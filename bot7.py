#!/usr/bin/env python3
"""
ai_terminal.py - AI Executor CLI (Version A, local, internet-enabled, auto-learn)

Features:
- Interactive REPL chat with OpenRouter model (prompt.txt system prompt)
- Save conversation history to history.json
- Extract code blocks from model replies and auto-save to scripts/ (via !create)
- Auto-learn: scan scripts/ → scripts_metadata.json → inject into system prompt
- Commands: !run, !create, !list, !scan <path>, !download <url>, !history, !clearhistory, !exit
- Logging to ai_exec.log
- Supports downloading scripts from GitHub via !download <url>
- Auto-fix Python indentation when saving scripts
- REPL interface uses [AI] / [USER] labels and colored output

FIX (v1.3 - SITUATIONAL INSTINCT):
- **FIXED BUG:** Filtered out false code blocks (short blocks without language tag)
- **FIXED BUG:** Implemented logic to auto-save code blocks when user explicitly asks for the file (e.g., "berikan file nya")
- Code interaction is now strictly governed by "FILE PROVISIONING RULES".
"""
import os, sys, re, json, shlex, subprocess, requests, time
from datetime import datetime, timezone
from typing import List, Tuple, Dict, Optional
from urllib.parse import urlparse

# ------------------ Configuration ------------------
API_URL = os.getenv("OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = os.getenv("OPENROUTER_MODEL", "minimax/minimax-m2:free")
PROMPT_FILE = os.getenv("PROMPT_FILE", "prompt.txt")
HISTORY_FILE = os.getenv("HISTORY_FILE", "history.json")
SCRIPTS_DIR = os.getenv("SCRIPTS_DIR", "scripts")
LOGFILE = os.getenv("AI_EXEC_LOG", "ai_exec.log")
METADATA_FILE = os.getenv("SCRIPTS_METADATA", "scripts_metadata.json")
MODEL_TEMPERATURE = float(os.getenv("MODEL_TEMPERATURE", "0.0"))
MODEL_MAX_TOKENS = int(os.getenv("MODEL_MAX_TOKENS", "1000"))
HEAD_LINES = int(os.getenv("SCRIPT_HEAD_LINES", "10"))
METADATA_SAMPLE_LIMIT = int(os.getenv("METADATA_SAMPLE_LIMIT", "40"))
DEFAULT_TIMEOUT = int(os.getenv("DEFAULT_TIMEOUT", "180"))

# ------------------ Utilities ------------------
LANG_TO_EXT = {
    "python": ".py", "py": ".py",
    "javascript": ".js", "js": ".js",
    "bash": ".sh", "sh": ".sh",
    "html": ".html", "css": ".css",
    "java": ".java", "c": ".c", "cpp": ".cpp", "c++": ".cpp",
    "rust": ".rs", "go": ".go",
    "json": ".json", "sql": ".sql",
    "ts": ".ts", "typescript": ".ts",
    "txt": ".txt", # Ditambahkan untuk menangani blok teks umum
}
CODE_FENCE_RE = re.compile(r"```(?:([a-zA-Z0-9_+-]+)\n)?(.*?)```", re.DOTALL)
THINK_RE = re.compile(r"<think>.*?</think>|<thinking>.*?</thinking>", re.IGNORECASE|re.DOTALL)

def now_ts(): return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

# ------------------ I/O ------------------
def load_prompt() -> str:
    if not os.path.exists(PROMPT_FILE):
        return "You are a local AI assistant for lab/CTF. Be concise and safe."
    with open(PROMPT_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()
DEFAULT_PROMPT = load_prompt()

def log(entry: Dict):
    entry_line = {"ts": now_ts()}
    entry_line.update(entry)
    try:
        with open(LOGFILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry_line, ensure_ascii=False) + "\n")
    except: pass

# ------------------ History ------------------
def load_history() -> Dict:
    if os.path.exists(HISTORY_FILE):
        try:
            return json.load(open(HISTORY_FILE,"r",encoding="utf-8"))
        except: pass
    return {"session":[]}
def save_history(history: Dict):
    try:
        tmp = HISTORY_FILE+".tmp"
        with open(tmp,"w",encoding="utf-8") as f:
            json.dump(history,f,ensure_ascii=False,indent=2)
        os.replace(tmp,HISTORY_FILE)
    except Exception as e: log({"event":"history_save_failed","error":str(e)})

# ------------------ Text utilities (MODIFIED) ------------------
def strip_internal_thoughts(text: str) -> str:
    cleaned = THINK_RE.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()

# MODIFIED: Menambahkan filter untuk mencegah blok kode palsu (noise)
def extract_code_blocks(text: str) -> List[Tuple[str,str]]:
    blocks=[]
    for m in CODE_FENCE_RE.finditer(text):
        lang=(m.group(1) or "").strip()
        code=m.group(2).rstrip()
        
        # FIX: Filter blok kode palsu: Terlalu pendek (kurang dari 30 karakter) 
        # DAN tidak memiliki penanda bahasa eksplisit (lang)
        if not lang and len(code.splitlines()) <= 1 and len(code) < 30:
            continue
            
        blocks.append((lang.lower(),code))
    return blocks

def choose_filename_from_user_msg(user_msg: str, lang_hint: str, idx:int=0) -> str:
    # Fungsi ini sekarang utamanya digunakan oleh !create, 
    # atau sebagai fallback untuk 'y' di prompt interaktif
    m = re.search(r"(?:nama file|file named|save as|simpan sebagai)\s+([^\s.,;:]+)",user_msg,flags=re.IGNORECASE)
    if m: return m.group(1)
    
    ext = LANG_TO_EXT.get(lang_hint.lower(), ".txt")
    # Menggunakan timestamp agar unik, bukan hanya index
    return f"script{int(time.time())}_{idx+1}{ext}"

# ------------------ Scripts ------------------
def ensure_scripts_dir(): os.makedirs(SCRIPTS_DIR,exist_ok=True)
def list_scripts()->List[str]:
    ensure_scripts_dir()
    return sorted([f for f in os.listdir(SCRIPTS_DIR) if os.path.isfile(os.path.join(SCRIPTS_DIR,f)) and os.access(os.path.join(SCRIPTS_DIR,f),os.X_OK)])

def fix_python_indentation(code:str)->str:
    """Simple auto-indent fixer: adds 4 spaces after for/if/def/try/etc if next line not indented"""
    lines = code.splitlines()
    fixed_lines=[]
    current_indent = 0 # Track current indentation level
    
    for i,line in enumerate(lines):
        stripped=line.lstrip()
        if not stripped:
            fixed_lines.append(line)
            continue
            
        line_indent = len(line) - len(stripped)
        
        if line_indent < current_indent:
            current_indent = line_indent
        
        if i>0 and lines[i-1].rstrip().endswith(":") and line_indent <= current_indent:
            prev_line_indent = len(lines[i-1]) - len(lines[i-1].lstrip())
            line = " " * (prev_line_indent + 4) + stripped
            line_indent = len(line) - len(stripped)
        
        fixed_lines.append(line)

        if stripped.endswith(":"):
            current_indent = line_indent + 4
        elif line_indent > current_indent:
            current_indent = line_indent

    return "\n".join(fixed_lines)

# MODIFIED: Ditambahkan 'force_name' untuk prompt interaktif (sama seperti sebelumnya)
def save_code_file(code:str, lang:str, user_msg:str, idx:int=0, force_name:Optional[str]=None)->str:
    ensure_scripts_dir()
    if lang.lower() in ("python","py"):
        code = fix_python_indentation(code)
    
    if force_name:
        name = force_name
    else:
        # Fallback ke perilaku lama (untuk !create atau jika user_msg mengandung nama)
        name = choose_filename_from_user_msg(user_msg, lang, idx)
        
    name=re.sub(r'[^A-Za-z0-9_.-]','',name)
    # Tambahkan ekstensi jika nama paksa tidak memilikinya
    if force_name and '.' not in name and lang:
        name += LANG_TO_EXT.get(lang, ".txt")
        
    path=os.path.join(SCRIPTS_DIR,name)
    
    # Handle collision
    if os.path.exists(path):
        base,ext=os.path.splitext(name)
        path=os.path.join(SCRIPTS_DIR,f"{base}_{int(time.time())}{ext}") 
        
    with open(path,"w",encoding="utf-8") as f: f.write(code)
    if path.endswith((".py",".sh")):
        try: os.chmod(path,0o755)
        except Exception as e: log({"event":"chmod_failed","path":path,"error":str(e)})
    return path

# ------------------ OpenRouter ------------------
def call_openrouter_system(user_text:str, history_messages:List[Dict], scripts_metadata_summary:Optional[str]=None)->str:
    if not OPENROUTER_KEY: raise RuntimeError("OPENROUTER_API_KEY not set.")
    headers = {"Authorization":f"Bearer {OPENROUTER_KEY}","Content-Type":"application/json"}
    
    system_prompt = scripts_metadata_summary + "\n\n" + DEFAULT_PROMPT if scripts_metadata_summary else DEFAULT_PROMPT
    
    messages = [{"role":"system","content":system_prompt}]+history_messages[-48:]+[{"role":"user","content":user_text}]
    payload={"model":MODEL,"messages":messages,"max_tokens":MODEL_MAX_TOKENS,"temperature":MODEL_TEMPERATURE}
    try:
        res=requests.post(API_URL,json=payload,headers=headers,timeout=60)
        res.raise_for_status()
        data=res.json()
        if "choices" in data and data["choices"]: return data["choices"][0]["message"]["content"]
        return "⚠️ Gagal mendapatkan respon dari OpenRouter."
    except Exception as e:
        log({"event":"api_error","error":str(e)})
        return f"⚠️ Error calling OpenRouter: {e}"

# ------------------ Auto-learn metadata (Sama seperti sebelumnya) ------------------
def read_head(path:str,lines:int=HEAD_LINES)->str:
    try:
        with open(path,"r",encoding="utf-8",errors="ignore") as f:
            return "".join([f.readline() for _ in range(lines)])
    except: return ""

def build_metadata_prompt(samples:List[Dict])->str:
    prompt=("You are given a set of local script files. Summarize each as JSON with fields: path, lang, head, ai_summary, usage_examples, risk_notes. The 'usage_examples' must be an array of full executable command lines. Be concise.\nFiles:\n")
    for s in samples:
        prompt+=f"---\nPATH:{s['path']}\nHEAD:\n{s['head'][:2000]}\n"
    prompt+="\nOutput JSON array now."
    return prompt

def parse_json_safe(text:str)->Optional[object]:
    try:
        start=text.find("[")
        if start!=-1:
            for end in range(len(text),start,-1):
                try: 
                    if text[end-1] in ("]", "}"):
                        return json.loads(text[start:end])
                except: continue
        return json.loads(text) 
    except: return None

def scan_and_generate_metadata(target_path:Optional[str]=None)->List[Dict]:
    search_path=target_path or SCRIPTS_DIR
    if not os.path.exists(search_path): return []
    candidates=[]
    for root,_,files in os.walk(search_path):
        for fn in files:
            full=os.path.join(root,fn)
            rel=os.path.relpath(full)
            if os.path.isfile(full) and (fn.endswith((".py",".sh",".pl",".rb")) or os.access(full,os.X_OK)):
                candidates.append({"path":rel,"lang":os.path.splitext(fn)[1].lstrip("."),
                                   "head":read_head(full)})
    if not candidates: return []
    
    batch=candidates[:METADATA_SAMPLE_LIMIT]
    prompt=build_metadata_prompt(batch)
    
    raw=call_openrouter_system(prompt,[],None)
    cleaned=strip_internal_thoughts(raw)
    parsed=parse_json_safe(cleaned)
    metadata=[]
    
    if isinstance(parsed,list):
        for item in parsed:
            try:
                metadata.append({
                    "path":item.get("path",""),
                    "lang":item.get("lang",""),
                    "head":item.get("head","")[:2000],
                    "ai_summary":item.get("ai_summary","")[:500],
                    "usage_examples":item.get("usage_examples",[])[:5],
                    "risk_notes":item.get("risk_notes","")[:300]
                })
            except: continue
    else:
        for s in batch: metadata.append({"path":s["path"],"lang":s.get("lang",""),"head":s["head"][:2000],
                                         "ai_summary":cleaned[:500],"usage_examples":[],"risk_notes":""})
                                         
    try:
        with open(METADATA_FILE,"w",encoding="utf-8") as f: json.dump(metadata,f,ensure_ascii=False,indent=2)
    except Exception as e: log({"event":"metadata_save_failed","error":str(e)})
    log({"event":"metadata_generated","count":len(metadata)})
    return metadata

def load_metadata_summary_for_prompt(max_entries:int=12)->Optional[str]:
    if not os.path.exists(METADATA_FILE): return None
    try: metadata=json.load(open(METADATA_FILE,"r",encoding="utf-8"))
    except: return None
    if not metadata: return None
    
    parts=["**AVAILABLE SCRIPTS:** You have access to the following local script files in your 'scripts/' directory. Use them if they are relevant to the user's request. Always suggest the specific file path from the list below if you recommend a script to be run or inspected. Use !run <script_name> to execute.\n"]
    
    for item in metadata[:max_entries]:
        p=item.get("path","")
        s=item.get("ai_summary","")
        u=item.get("usage_examples",[None])
        
        example_str = f"Example: `!run {p} {u[0]}`" if u and isinstance(u[0], str) else ""
        
        parts.append(f"- **{p}** ({item.get('lang', 'unk')}): {s}. {example_str}")
        
    return "\n".join(parts)

# ------------------ Execution (Sama seperti sebelumnya) ------------------
def build_exec_list(tool:str,args:List[str])->List[str]:
    ensure_scripts_dir()
    scripts=list_scripts()
    if tool in scripts: return [os.path.join(SCRIPTS_DIR,tool)]+args
    if os.path.isfile(tool): return [tool]+args
    return [tool]+args

def run_local(cmd_list:List[str],timeout:int=DEFAULT_TIMEOUT)->Tuple[int,str,str,bool]:
    try:
        proc=subprocess.run(cmd_list,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,check=False)
        return proc.returncode,proc.stdout.decode(errors="replace"),proc.stderr.decode(errors="replace"),False
    except subprocess.TimeoutExpired:
        return -1,"","TIMEOUT",True
    except Exception as e:
        return -1,"",f"EXEC_ERROR: {e}",False

# ------------------ GitHub download (Sama seperti sebelumnya) ------------------
def download_github_file(url:str)->Optional[str]:
    parsed=urlparse(url)
    raw_url = None

    if parsed.netloc == "github.com":
        path_parts=parsed.path.strip("/").split("/")
        if len(path_parts) >= 5 and path_parts[2] == "blob":
            user,repo,_,branch,*file_path=path_parts
            raw_url=f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{'/'.join(file_path)}"
        else:
            log({"event":"github_download_failed","url":url,"error":"URL GitHub tidak mengarah ke file blob."})
            return None
    elif parsed.netloc == "raw.githubusercontent.com":
        raw_url = url
    else:
        log({"event":"github_download_failed","url":url,"error":"Bukan URL GitHub atau Raw GitHub yang valid."})
        return None

    if not raw_url:
        return None

    try:
        url_path = urlparse(raw_url).path
        fname = os.path.basename(url_path)
        if not fname:
            fname = "downloaded_script"
    except:
        fname = "downloaded_script"

    ensure_scripts_dir()
    path=os.path.join(SCRIPTS_DIR,fname)
    if os.path.exists(path):
        base,ext=os.path.splitext(fname)
        path=os.path.join(SCRIPTS_DIR,f"{base}_{int(time.time())}{ext}")

    try:
        r=requests.get(raw_url,timeout=30)
        r.raise_for_status()
        with open(path,"wb") as f: f.write(r.content)
        if path.endswith((".py",".sh")):
            os.chmod(path,0o755)
        return path
    except Exception as e:
        log({"event":"github_download_failed","url":url,"error":str(e)})
        return None


# ------------------ REPL handlers ------------------

def print_bubble(role:str,text:str):
    if role.lower() == "ai":
        print(f"\033[91m[AI]\033[0m \033[31m{text}\033[0m\n")
    else:
        print(f"\033[92m[USER]\033[0m {text}\033[0m\n") # FIX: Menambahkan reset color

def print_code_box(code: str, lang: str, idx: int):
    """Mencetak kotak visual untuk memisahkan kode dari chat."""
    lang = lang or "code"
    label = f" KODE BLOCK #{idx+1} ({lang}) "
    width = 70
    
    # Warna kuning untuk kotak
    print(f"\n\033[93m{''.center(width, '—')}\033[0m") 
    print(f"\033[93m|{label.center(width-2)}|\033[0m")
    print(f"\033[93m{''.center(width, '—')}\033[0m")
    
    # Kode di dalam (tanpa warna tambahan agar jelas)
    print(code) 
    
    print(f"\033[93m{''.center(width, '—')}\033[0m")


# MODIFIED: Logika chat diubah total untuk menerapkan Insting Situasional
def handle_chat_input(user_text:str,history:Dict,metadata_summary:Optional[str]):
    # ------------------ Auto-Save Trigger Check (Instinct 8) ------------------
    is_explicit_save_request = re.search(r"(berikan file|buat dalam file|simpan ini|save it|berikan kode|berikan script)", user_text, re.IGNORECASE)
    
    last_assistant_msg = history.get("session", [])[-1]["content"] if history.get("session", []) else ""
    
    # Jika permintaan saat ini eksplisit untuk save, dan balasan AI sebelumnya berisi kode:
    if is_explicit_save_request and CODE_FENCE_RE.search(last_assistant_msg):
        print_bubble("user", user_text)
        code_blocks = extract_code_blocks(last_assistant_msg)
        
        if not code_blocks:
            print("[!] Tidak ada kode yang ditemukan di balasan AI terakhir untuk disimpan.")
            return

        print(f"\n[AI menemukan {len(code_blocks)} code block(s) dari balasan sebelumnya. Menyimpan otomatis.]")
        # Mengambil user_text dari turn sebelumnya untuk penamaan yang lebih baik
        prev_user_text = history.get("session", [])[-2].get("content", "") if len(history.get("session", [])) >= 2 else ""
        
        for idx, (lang, code) in enumerate(code_blocks):
            print_code_box(code, lang, idx)
            # Auto-Save: menggunakan prev_user_text sebagai konteks nama
            path = save_code_file(code, lang, prev_user_text, idx)
            print(f"[AUTO-SAVED] -> {path}")
            
        # Simpan interaksi ini ke history
        history.setdefault("session",[]).append({"role":"user","content":user_text})
        save_history(history)
        return

    # ------------------ Normal Chat & Code Generation ------------------
    # Panggil OpenRouter
    raw=call_openrouter_system(user_text,history.get("session",[]),metadata_summary)
    cleaned=strip_internal_thoughts(raw)
    history.setdefault("session",[]).append({"role":"user","content":user_text})
    history.setdefault("session",[]).append({"role":"assistant","content":cleaned})
    save_history(history)
    log({"event":"chat","input_preview":user_text[:200],"reply_preview":cleaned[:200]})
    
    code_blocks = extract_code_blocks(cleaned)
    text_without_code = CODE_FENCE_RE.sub("", cleaned).strip()

    # 1. Tampilkan bubble user
    print_bubble("user", user_text)
    
    # 2. Tampilkan bubble AI (hanya teks)
    if text_without_code:
        print_bubble("ai", text_without_code)

    # 3. Tampilkan Kode & Interaktif Simpan (Instinct 8: Default Mode)
    if code_blocks:
        # Cek apakah pengguna secara eksplisit meminta kode/script di turn ini.
        # Ini mencegah AI menampilkan kode hanya untuk menjelaskan konsep (Instinct 9).
        is_code_explicitly_requested = re.search(r"(kode|script|payload|program|tool|buatkan|tampilkan)", user_text, re.IGNORECASE)

        if not is_code_explicitly_requested and not re.search(r"(apa|jelaskan|defenisi)", user_text, re.IGNORECASE):
            # Jika user HANYA bertanya 'apa' atau 'jelaskan', dan AI merespons dengan kode,
            # dan user TIDAK meminta kode secara eksplisit (is_code_explicitly_requested=False),
            # kita bisa memilih untuk TIDAK menanyakan simpan secara interaktif,
            # TAPI karena kita ingin user KONTROL, kita tetap tanyakan interaktif.
            # Filternya adalah PADA PROMPT AI. Jika prompt AI gagal, kita tetap tanyakan user.
            pass

        print(f"\n[AI menemukan {len(code_blocks)} code block(s)]")
        for idx, (lang, code) in enumerate(code_blocks):
            print_code_box(code, lang, idx)
            
            # Tampilkan prompt untuk menyimpan
            try:
                save_choice = input(f"\033[92mSimpan code block #{idx+1}? (y/n/nama_file): \033[0m").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n[Input dibatalkan]")
                continue

            if save_choice.lower() == 'y':
                path = save_code_file(code, lang, user_text, idx)
                print(f"[SAVED] -> {path}")
            elif save_choice and save_choice.lower() != 'n':
                path = save_code_file(code, lang, user_text, idx, force_name=save_choice)
                print(f"[SAVED] -> {path}")
            else:
                print("[SKIPPED] Code block tidak disimpan.")
        print() 


def handle_create_cmd(filename:Optional[str],history:Dict,metadata_summary:Optional[str]):
    prompt_filename=filename or "(none)"
    user_prompt=input("Describe script to create (detailed):\n> ").strip()
    instruction=f"Generate full content for a script. Filename suggestion: {prompt_filename}. Output code in triple-backticks and one-line explanation after code.\n\n{user_prompt}"
    raw=call_openrouter_system(instruction,history.get("session",[]),metadata_summary)
    cleaned=strip_internal_thoughts(raw)
    code_blocks=extract_code_blocks(cleaned)
    
    print_bubble("user", user_prompt)
    
    if not code_blocks:
        print("[!] Model did not return code blocks. Showing raw output:")
        print_bubble("ai",cleaned)
        return
        
    # Perilaku !create tetap sama: auto-save
    for idx,(lang,code) in enumerate(code_blocks):
        path=save_code_file(code,lang,user_prompt,idx)
        print(f"[CREATED] {path}")
        
    history.setdefault("session",[]).append({"role":"user","content":user_prompt})
    history.setdefault("session",[]).append({"role":"assistant","content":cleaned})
    save_history(history)
    log({"event":"create_script","filename":filename or "","created_count":len(code_blocks)})

def handle_run_cmd(rest:str,history:Dict,metadata_summary:Optional[str]):
    parts=shlex.split(rest)
    if not parts: print("Usage: !run <tool_or_script> [args...]"); return
    tool,args=parts[0],parts[1:]
    cmd_list=build_exec_list(tool,args)
    print(f"[EXEC] {shlex.join(cmd_list)}")
    rc,out,err,timed_out=run_local(cmd_list)
    print("=== OUTPUT ===")
    if out: print(out.rstrip())
    if err: print("--- STDERR ---"); print(err.rstrip())
    if timed_out: print(f"--- TIMEOUT --- Command timed out after {DEFAULT_TIMEOUT} seconds.")
    if rc != 0 and rc != -1 and not timed_out: print(f"--- EXIT CODE --- {rc}")
    
    # Tambahkan hasil eksekusi ke riwayat
    history.setdefault("session",[]).append({"role":"user","content":f"!run {rest}"})
    history.setdefault("session",[]).append({"role":"assistant","content":f"EXEC_RESULT (RC:{rc}, Timeout:{timed_out}):\nSTDOUT:\n{out[:500]} \nSTDERR:\n{err[:500]}"})
    save_history(history)
    log({"event":"exec","cmd":cmd_list,"exit_code":rc,"timed_out":timed_out,"stdout_snippet":out[:500],"stderr_snippet":err[:500]})
    
    # Panggil AI untuk penjelasan output (opsional, untuk interaksi yang lebih dalam)
    if out or err:
        explain_prompt = f"The previous command (`{shlex.join(cmd_list)}`) was executed. Exit Code: {rc}. STDOUT:\n{out[:1000]}\nSTDERR:\n{err[:1000]}. Explain important findings briefly (max 2 sentences)."
        explanation_raw = call_openrouter_system(explain_prompt, history.get("session", []), metadata_summary)
        explanation = strip_internal_thoughts(explanation_raw)
        
        print(f"\n\033[94m[AI ANALYSIS]\033[0m {explanation}\033[0m")
        history.setdefault("session",[]).append({"role":"assistant","content":f"AI_ANALYSIS: {explanation}"})
        save_history(history)


def handle_scan_cmd(rest:str,history:Dict):
    path=rest.strip() or SCRIPTS_DIR
    print(f"[SCANNING] {path}...")
    metadata=scan_and_generate_metadata(path)
    print(f"[SUCCESS] Generated metadata for {len(metadata)} scripts.")
    if metadata:
        log({"event":"metadata_generated","count":len(metadata)})
    else:
        print("[INFO] No executable scripts found.")

def handle_download_cmd(rest:str):
    url=rest.strip()
    if not url: print("Usage: !download <github_file_url>"); return
    print(f"[DOWNLOADING] from {url}...")
    path=download_github_file(url)
    if path:
        print(f"[DOWNLOADED] Saved as: {path}")
    else:
        print("[!] Download failed. Check log for details")

def handle_list_cmd(rest:str):
    metadata=load_metadata_summary_for_prompt(max_entries=20)
    if metadata:
        print("\n--- Available Scripts and Metadata ---")
        print(metadata)
        print("--------------------------------------\n")
    else:
        print("No scripts or metadata found. Use `!scan` to generate metadata.")

def handle_history_cmd(rest:str):
    hist=load_history().get("session",[])
    if not hist: print("History is empty."); return
    try: limit=int(rest.strip()) if rest.strip() else 20
    except: limit=20
    
    print("\n--- Conversation History (Last {}) ---".format(limit))
    for entry in hist[-limit:]:
        role = entry["role"].upper()
        content = entry["content"]
        if role == "USER": print(f"\033[92m[{role}]\033[0m {content[:100]}...")
        else: print(f"\033[91m[{role}]\033[0m {content[:100]}...")
    print("--------------------------------------\n")
    
def handle_clear_history(rest:str):
    if rest.strip().lower() == "yes":
        save_history({"session":[]})
        print("[CLEARED] History has been reset.")
    else:
        print("Use `!clearhistory yes` to confirm clearing all history.")


COMMANDS = {
    "!run": handle_run_cmd,
    "!create": handle_create_cmd,
    "!scan": handle_scan_cmd,
    "!download": handle_download_cmd,
    "!list": handle_list_cmd,
    "!history": handle_history_cmd,
    "!clearhistory": handle_clear_history,
}

# ------------------ REPL ------------------
def repl():
    print(f"\n{'-'*50}")
    print(f"AI Executor CLI (v1.3 - Python {sys.version.split()[0]})")
    print(f"Model: {MODEL} | API: OpenRouter")
    print("Type `!list`, `!run`, `!create`, or `!exit`.")
    print(f"{'-'*50}\n")
    
    history=load_history()
    
    while True:
        try:
            metadata_summary=load_metadata_summary_for_prompt()
            
            user_input=input("~/cliai $ ").strip()
            if not user_input: continue
            
            if user_input.lower() in ("!exit","!quit","exit"): break
            
            # Perintah khusus
            cmd_match=re.match(r"(\![a-z]+)\s*(.*)",user_input,re.IGNORECASE)
            if cmd_match:
                cmd,rest=cmd_match.groups()
                handler=COMMANDS.get(cmd.lower())
                if handler:
                    # Perintah !create dan !run membutuhkan akses ke history/metadata
                    if cmd.lower() in ("!create","!run"):
                         handler(rest,history,metadata_summary)
                    elif cmd.lower() in ("!scan","!history","!clearhistory"):
                         handler(rest,history)
                    else: # !download, !list
                         handler(rest)
                else:
                    print(f"Unknown command: {cmd}. Use `!list` for available scripts or `!history`.")
            else:
                # Obrolan biasa
                handle_chat_input(user_input,history,metadata_summary)
                
        except EOFError:
            print("\nExiting...")
            break
        except KeyboardInterrupt:
            print("\nInterrupt received. Type `!exit` to close.")
            continue
        except RuntimeError as e:
            print(f"🚨 FATAL ERROR: {e}")
            break

if __name__ == "__main__":
    if not os.path.exists(SCRIPTS_DIR):
        os.makedirs(SCRIPTS_DIR, exist_ok=True)
        # Tambahkan file placeholder atau contoh jika perlu
    
    repl()
