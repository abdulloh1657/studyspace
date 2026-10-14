import random
import re
import sqlite3
from datetime import date
from flask import Flask, render_template, request, redirect

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024


def init_db():
    conn = sqlite3.connect("data.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transaksi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            jenis TEXT,
            kategori TEXT,
            jumlah INTEGER,
            tanggal TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jadwal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama TEXT,
            jenis TEXT,
            tanggal TEXT,
            mulai TEXT,
            selesai TEXT,
            catatan TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rangkuman (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            judul TEXT,
            matkul TEXT,
            isi TEXT,
            tanggal TEXT
        )
    """)
    conn.commit()
    conn.close()


init_db()


def ekstrak_teks(file):
    nama = file.filename.lower()
    try:
        if nama.endswith(".txt") or nama.endswith(".md"):
            return file.read().decode("utf-8", errors="ignore")
        if nama.endswith(".pdf"):
            from pypdf import PdfReader
            pembaca = PdfReader(file.stream)
            return "\n".join((h.extract_text() or "") for h in pembaca.pages)
        if nama.endswith(".docx"):
            from docx import Document
            dokumen = Document(file.stream)
            return "\n".join(p.text for p in dokumen.paragraphs)
    except Exception:
        return ""
    return ""


KATA_UMUM = {
    "adalah", "merupakan", "dengan", "untuk", "dalam", "dapat", "karena",
    "tetapi", "sebagai", "dimana", "yaitu", "yakni", "serta", "antara",
    "terhadap", "tersebut", "sehingga", "secara", "bahwa", "kepada",
    "setiap", "semua", "lebih", "hanya", "setelah", "sebelum", "ketika",
    "namun", "harus", "telah", "sudah", "masih", "dalam", "pada",
}


def buat_soal(teks, maks=10):
    teks = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", teks)
    teks = re.sub(r"\s*\n\s*", " ", teks)
    kalimat_list = re.split(r"(?<=[.!?])\s+", teks)
    soal = []
    for kalimat in kalimat_list:
        kalimat = kalimat.strip()
        jumlah_kata = len(kalimat.split())
        if jumlah_kata < 6 or jumlah_kata > 30:
            continue
        if not kalimat[0].isupper() or kalimat[-1] not in ".!?":
            continue
        kata = re.findall(r"[A-Za-z]{5,}", kalimat)
        kandidat = [k for k in kata if k.lower() not in KATA_UMUM]
        if not kandidat:
            continue
        kunci = max(kandidat, key=len)
        kosong = re.sub(r"\b" + re.escape(kunci) + r"\b", "_____", kalimat, count=1)
        soal.append({"kalimat": kosong, "kunci": kunci})
    random.shuffle(soal)
    return soal[:maks]


@app.route("/")
def beranda():
    return render_template("index.html")


@app.route("/keuangan", methods=["GET", "POST"])
def keuangan():
    conn = sqlite3.connect("data.db")
    if request.method == "POST":
        jenis = request.form["jenis"]
        kategori = request.form["kategori"]
        jumlah = int(request.form["jumlah"])
        tanggal = request.form["tanggal"]
        conn.execute(
            "INSERT INTO transaksi (jenis, kategori, jumlah, tanggal) VALUES (?, ?, ?, ?)",
            (jenis, kategori, jumlah, tanggal)
        )
        conn.commit()
        conn.close()
        return redirect("/keuangan")

    bulan = request.args.get("bulan") or date.today().strftime("%Y-%m")
    pola = bulan + "%"

    daftar = conn.execute(
        "SELECT jenis, kategori, jumlah, tanggal, id FROM transaksi WHERE tanggal LIKE ? ORDER BY tanggal DESC, id DESC",
        (pola,)
    ).fetchall()

    total_masuk, total_keluar = conn.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN jenis = 'pemasukan' THEN jumlah END), 0),
            COALESCE(SUM(CASE WHEN jenis = 'pengeluaran' THEN jumlah END), 0)
        FROM transaksi
        WHERE tanggal LIKE ?
    """, (pola,)).fetchone()
    conn.close()

    saldo = total_masuk - total_keluar
    return render_template(
        "keuangan.html",
        daftar=daftar,
        total_masuk=total_masuk,
        total_keluar=total_keluar,
        saldo=saldo,
        bulan=bulan
    )


@app.route("/hapus/<int:id>", methods=["POST"])
def hapus(id):
    conn = sqlite3.connect("data.db")
    conn.execute("DELETE FROM transaksi WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect("/keuangan")


@app.route("/jadwal", methods=["GET", "POST"])
def jadwal():
    if request.method == "POST":
        nama = request.form["nama"]
        jenis = request.form["jenis"]
        tanggal = request.form["tanggal"]
        mulai = request.form["mulai"]
        selesai = request.form["selesai"]
        catatan = request.form["catatan"]

        conn = sqlite3.connect("data.db")
        conn.execute(
            "INSERT INTO jadwal (nama, jenis, tanggal, mulai, selesai, catatan) VALUES (?, ?, ?, ?, ?, ?)",
            (nama, jenis, tanggal, mulai, selesai, catatan)
        )
        conn.commit()
        conn.close()
        return redirect("/jadwal")

    conn = sqlite3.connect("data.db")
    daftar = conn.execute(
        "SELECT nama, jenis, tanggal, mulai, selesai, catatan, id FROM jadwal ORDER BY tanggal ASC, mulai ASC"
    ).fetchall()
    conn.close()
    return render_template("jadwal.html", daftar=daftar)


@app.route("/hapus-jadwal/<int:id>", methods=["POST"])
def hapus_jadwal(id):
    conn = sqlite3.connect("data.db")
    conn.execute("DELETE FROM jadwal WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect("/jadwal")


@app.route("/rangkuman", methods=["GET", "POST"])
def rangkuman():
    if request.method == "POST":
        judul = request.form["judul"]
        matkul = request.form["matkul"]
        isi = request.form["isi"].strip()
        file = request.files.get("file")
        if file and file.filename:
            isi = (isi + "\n\n" + ekstrak_teks(file)).strip()
        if not isi:
            return redirect("/rangkuman")
        tanggal = date.today().isoformat()

        conn = sqlite3.connect("data.db")
        conn.execute(
            "INSERT INTO rangkuman (judul, matkul, isi, tanggal) VALUES (?, ?, ?, ?)",
            (judul, matkul, isi, tanggal)
        )
        conn.commit()
        conn.close()
        return redirect("/rangkuman")

    conn = sqlite3.connect("data.db")
    daftar = conn.execute(
        "SELECT judul, matkul, tanggal, id FROM rangkuman ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return render_template("rangkuman.html", daftar=daftar)


@app.route("/rangkuman/<int:id>")
def baca_rangkuman(id):
    conn = sqlite3.connect("data.db")
    r = conn.execute(
        "SELECT judul, matkul, tanggal, isi FROM rangkuman WHERE id = ?", (id,)
    ).fetchone()
    conn.close()
    if r is None:
        return redirect("/rangkuman")
    return render_template("baca_rangkuman.html", r=r, id=id)


@app.route("/hapus-rangkuman/<int:id>", methods=["POST"])
def hapus_rangkuman(id):
    conn = sqlite3.connect("data.db")
    conn.execute("DELETE FROM rangkuman WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect("/rangkuman")


@app.route("/latihan")
def latihan():
    conn = sqlite3.connect("data.db")
    daftar = conn.execute(
        "SELECT judul, matkul, id FROM rangkuman ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return render_template("latihan.html", daftar=daftar)


@app.route("/latihan/<int:id>", methods=["GET", "POST"])
def kerjakan(id):
    conn = sqlite3.connect("data.db")
    r = conn.execute(
        "SELECT judul, matkul, isi FROM rangkuman WHERE id = ?", (id,)
    ).fetchone()
    conn.close()
    if r is None:
        return redirect("/latihan")

    if request.method == "POST":
        total = int(request.form["jumlah"])
        hasil = []
        benar = 0
        for i in range(total):
            kalimat = request.form["kalimat" + str(i)]
            kunci = request.form["kunci" + str(i)]
            jawab = request.form.get("jawab" + str(i), "").strip()
            cocok = jawab.lower() == kunci.lower()
            if cocok:
                benar += 1
            hasil.append({"kalimat": kalimat, "kunci": kunci, "jawab": jawab, "cocok": cocok})
        return render_template("kerjakan.html", r=r, id=id, hasil=hasil, benar=benar, total=total)

    soal = buat_soal(r[2])
    return render_template("kerjakan.html", r=r, id=id, soal=soal)


if __name__ == "__main__":
    app.run(debug=True)