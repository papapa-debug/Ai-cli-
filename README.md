# 🤖 Ai-cli: AI Executor Terminal (Executor)

**Ai-cli** (atau **Executor**) adalah asisten AI berbasis terminal yang **super proaktif**, dirancang untuk membantu Anda dalam **penetration testing**, **Capture The Flag (CTF)**, dan **administrasi sistem**.  
Ia dapat berinteraksi, menghasilkan, dan menjalankan skrip secara cerdas langsung dari terminal Anda — serta **belajar otomatis** dari alat dan skrip lokal Anda.

---

## ✨ Fitur Utama

| Fitur | Deskripsi |
|-------|------------|
| **Insting Situasional** | AI secara cerdas memutuskan apakah akan menampilkan kode atau langsung menyimpannya ke file berdasarkan konteks percakapan Anda. |
| **Auto-Learn (Memori)** | Secara otomatis memindai direktori `scripts/`, membuat ringkasan metadata, dan menyuntikkannya ke dalam system prompt AI. AI selalu memeriksa skrip lokal yang ada sebelum membuat yang baru. |
| **Analisis Output** | Setelah menjalankan perintah `!run`, AI menganalisis output yang dihasilkan dan memberikan ringkasan singkat. |
| **Command REPL** | Dilengkapi dengan serangkaian perintah kuat: `!run`, `!create`, `!scan`, `!download`, `!list`, `!history`, `!clearhistory`, dan `!exit`. |
| **Modular & Konfigurasi Fleksibel** | Semua konfigurasi, termasuk system prompt, variabel lingkungan, dan direktori, dapat disesuaikan sepenuhnya. |

---

## 🚀 Instalasi di Termux (Android)

Ikuti langkah-langkah di bawah ini untuk menginstal dan menjalankan **Ai-cli** di lingkungan Termux Anda.

### 1️⃣ Instal Prasyarat
Pastikan Anda sudah memiliki `git` dan `python`.

```bash
pkg update && pkg upgrade -y
pkg install git python -y

2️⃣ Kloning Repositori

git clone https://github.com/papapa-debug/Ai-cli-.git
cd Ai-cli-

3️⃣ Instal Dependensi Python

pip install -r requirements.txt

4️⃣ Konfigurasi Variabel Lingkungan

Ai-cli menggunakan variabel lingkungan untuk mengelola kunci API dan pengaturan lainnya.
Ganti OPENROUTER_API_KEY dengan kunci API asli Anda.

# Ganti dengan kunci API OpenRouter Anda yang sebenarnya!
export OPENROUTER_API_KEY="sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# Model AI yang digunakan
export OPENROUTER_MODEL="minimax/minimax-m2:free"

# File konfigurasi dan log
export PROMPT_FILE="prompt.txt"
export HISTORY_FILE="history.json"
export SCRIPTS_DIR="scripts"
export AI_EXEC_LOG="ai_exec.log"

> 💡 Tips: Tambahkan baris di atas ke file ~/.bashrc atau ~/.zshrc agar variabel ini tersimpan permanen.




---

5️⃣ Jalankan Executor

Setelah semua siap, jalankan bot:

python3 bot7.py

Anda akan masuk ke REPL interaktif, dan AI siap bekerja untuk Anda.


---

⚙️ Perintah Utama (REPL)

Gunakan perintah-perintah berikut saat berada dalam sesi Ai-cli:

Perintah	Deskripsi

!run [skrip] [arg]	Menjalankan skrip dari scripts/ atau perintah sistem (!run ls -la).
!create	Meminta AI membuat dan menyimpan skrip baru ke scripts/.
!scan	Memindai ulang direktori scripts/ untuk memperbarui metadata AI.
!download [url]	Mengunduh skrip dari URL eksternal (misalnya GitHub Gist).
!list	Menampilkan daftar skrip yang diketahui AI.
!history	Menampilkan riwayat percakapan.
!clearhistory	Menghapus riwayat percakapan AI.
!exit	Keluar dari REPL.



---

🧠 Contoh Alur Kerja

> !create port_scanner
AI: Skrip baru port_scanner.py telah dibuat di scripts/
> !run port_scanner 192.168.1.1
AI: Menjalankan port_scanner pada target...
AI: Port 22, 80, dan 443 terbuka. Rangkuman tersimpan di ai_exec.log.


---

📝 Kontribusi

Kami sangat terbuka terhadap kontribusi komunitas!
Jika Anda menemukan bug, ingin menambahkan fitur, atau sekadar ingin meningkatkan dokumentasi:

Buka Issue

Kirimkan Pull Request


> Bersama kita bisa membuat AI terminal yang benar-benar badass. 😎




---

📄 Lisensi

Proyek ini dilisensikan di bawah MIT License.
Lihat file LICENSE untuk detail lengkap.


---

> ⚠️ Catatan: AI seperti Gemini, ChatGPT, atau model lainnya dapat membuat kesalahan. Gunakan dengan bijak — selalu verifikasi output sebelum digunakan dalam lingkungan produksi atau pengujian keamanan.



---

Kamu mau aku tambahkan **badge GitHub** (seperti “MIT License”, “Python 3.x”, “Made with ❤️ in Termux”, dll) biar tampilannya lebih keren di atas README juga?
