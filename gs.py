#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Galatasaraylılar Yurdu Huzur Evi - Hasta Görev Yönetim Sistemi
Tam sürüm - PyQt5 tek dosya
Geliştirilmiş Özellikler:
 - Tarih formatı: gün/ay/yıl, Türkçe takvim
 - Hasta fotoğrafı görünürlük sorunu çözüldü
 - Karşılama penceresi modernize edildi
 - Hasta yönetimi sekmesi kaldırıldı
 - Görev durumu parantez içinde gösteriliyor
 - Varsayılan hasta en küçük oda numaralı hasta
 - Gün içinde (08:00-20:00) ve akşam (20:00-08:00) görev ayrımı
 - Yeni görev ekle hastalar sekmesine taşındı
 - Modern tarih ve saat tasarımı
 - Vakti gelen görevler ayrı grupta, kırmızı-sarı geçiş (yapıldı/yapılmadı işaretlenene kadar)
 - Silme ve arşivleme için onay
 - Arşivlenmiş öğeler için silme düğmesi
 - Modern yurt ve geliştirici sekmeleri
 - Ekstra ayarlar (tamamlanmış görev görünürlük süresi, saat formatı, otomatik yenileme)
 - Açık tema kaldırıldı
 - Geliştirici sekmesinde developer.png kullanımı
 - Saat pasifleşmesi için Gün İçinde ve Akşam seçeneklerinde QTimeEdit devre dışı
 - Geliştirilmiş bildirim tasarımı (ortada, hasta fotoğrafı ile)
 - Bildirimi alınmış görevler vadesi geldiğinde "Vakti Gelenler"e taşınır
 - Görevlerde hasta adı ve soyadı gösterilir
 - İstatistikler: Günlük toplam, tamamlanmış, vakti gelen, gelecek 24 saat, iptal edilen
 - Görevlere opsiyonel bitiş tarihi ve "Kaç günde bir" tekrar türü eklendi
 - Takvimde "Kaç günde bir" tekrar türüne göre günler gösterilir
"""

import sys, os, sqlite3, json, io
from datetime import datetime, date, time, timedelta
from functools import partial

os.environ["QT_MAC_WANTS_LAYER"] = "1"

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QLocale
from PyQt5.QtGui import QPixmap, QFont, QIcon
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
    QProgressBar, QTabWidget, QMainWindow, QMessageBox, QTableWidget, QTableWidgetItem,
    QFileDialog, QComboBox, QLineEdit, QDateEdit, QTimeEdit, QCheckBox, QTextEdit,
    QGroupBox, QFormLayout, QScrollArea, QDialog, QCalendarWidget, QSlider, QHeaderView, QSpinBox
)

# Paths and resources
APP_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(APP_DIR, "data")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

DB_PATH = os.path.join(DATA_DIR, "huzurevi.db")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
LOGO_PATH = os.path.join(DATA_DIR, "GSYV_LOGO.png")
DEVELOPER_PHOTO_PATH = os.path.join(DATA_DIR, "developer.png")
DEFAULT_PATIENT_PHOTO_PATH = os.path.join(DATA_DIR, "default_patient.png")  # Varsayılan hasta fotoğrafı (opsiyonel)

# Default settings
DEFAULT_SETTINGS = {
    "theme": "Galatasaray",
    "font_size": 14,
    "notifications_enabled": True,
    "completed_task_timeout": 4,  # hours
    "clock_format": "24 Saat",
    "auto_refresh": True,
    "notification_duration": 10,  # seconds
    "day_start": "08:00",
    "day_end": "20:00",
    "night_start": "20:00",
    "night_end": "08:00"
}

# Themes
THEMES = {
    "Galatasaray": {
        "bg_start": "#C0392B", "bg_end": "#F1C40F",
        "button": "#C0392B", "button_hover": "#A93226",
        "table_bg": "#333333", "text": "#000000"
    },
    "Koyu": {
        "bg_start": "#1E1E1E", "bg_end": "#1E1E1E",
        "button": "#333333", "button_hover": "#555555",
        "table_bg": "#2B2B2B", "text": "#FFFFFF"
    }
}

TURKISH_MONTHS = {
    1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran",
    7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"
}

# Database helpers
def get_conn():
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    return conn

def init_db_and_migrate():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS patients (
        room_number TEXT PRIMARY KEY,
        name TEXT, surname TEXT, notes TEXT,
        photo BLOB, tc_no TEXT, birth_date TEXT, phone TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS archive_patients (
        room_number TEXT PRIMARY KEY,
        name TEXT, surname TEXT, notes TEXT,
        photo BLOB, tc_no TEXT, birth_date TEXT, phone TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_number TEXT,
        task TEXT,
        time TEXT,
        done INTEGER DEFAULT 0,
        repeat_type TEXT,
        time_type TEXT,
        date TEXT,
        end_date TEXT,
        cancelled INTEGER DEFAULT 0,
        repeat_days TEXT,
        repeat_interval INTEGER,
        notified INTEGER DEFAULT 0,
        completed_time TIMESTAMP
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS archive (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_number TEXT, task TEXT, time TEXT, date TEXT, end_date TEXT, time_type TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS task_completions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER,
        completion_date TEXT,
        FOREIGN KEY (task_id) REFERENCES tasks(id)
    )
    """)
    conn.commit()
    conn.close()

init_db_and_migrate()

# Settings
def load_settings():
    if not os.path.exists(SETTINGS_PATH):
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS.copy()
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            s = json.load(f)
    except Exception:
        s = DEFAULT_SETTINGS.copy()
    for k, v in DEFAULT_SETTINGS.items():
        if k not in s:
            s[k] = v
    return s

def save_settings(s):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)

# Splash Screen
class SplashScreen(QWidget):
    finished = pyqtSignal()
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        screen = QApplication.primaryScreen().size()
        w = max(800, screen.width()//2)
        h = max(600, screen.height()*60//100)
        self.setMinimumSize(w,h)
        self.main = QWidget(self)
        self.main.setGeometry(0,0,w,h)
        self.main.setStyleSheet("border-radius:20px;")
        layout = QVBoxLayout(self.main)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)

        self.logo = QLabel()
        self.logo.setFixedSize(200,200)
        if os.path.exists(LOGO_PATH):
            self.logo.setPixmap(QPixmap(LOGO_PATH).scaled(200,200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.logo.setText("LOGO\nYOK")
            self.logo.setAlignment(Qt.AlignCenter)
            self.logo.setStyleSheet("background:white; border:4px solid #F1C40F; font-size:24px;")
        layout.addWidget(self.logo, alignment=Qt.AlignCenter)

        self.title = QLabel("Galatasaraylılar Yurdu Huzur Evi")
        self.title.setFont(QFont("Helvetica", 28, QFont.Bold))
        self.title.setStyleSheet("color:#000000;")
        layout.addWidget(self.title, alignment=Qt.AlignCenter)

        self.welcome = QLabel("Sevgi Yuvamıza Hoş Geldiniz!")
        self.welcome.setFont(QFont("Helvetica", 18))
        self.welcome.setStyleSheet("color:#000000;")
        layout.addWidget(self.welcome, alignment=Qt.AlignCenter)

        self.yurt_info = QTextEdit()
        self.yurt_info.setReadOnly(True)
        self.yurt_info.setHtml("""
            <p style='text-align: center; color: #000000;'>
                <b>Galatasaraylılar Yurdu</b><br>
                500 yılı aşkın tarihiyle bir eğitim, kültür, sanat ve spor ocağı olan Galatasaray Lisesi’nden kaynaklanan kuruluşlardan biri olan Galatasaraylılar Yardımlaşma Vakfı tarafından 1977 yılında kurulmuştur.<br>
                Florya’da 5000 m² alana inşa edilmiş, otel konforunda odalar ve ferah ortak alanlarla hizmet vermektedir.
            </p>
        """)
        self.yurt_info.setStyleSheet("background: transparent; border: none; color: #000000;")
        self.yurt_info.setFixedHeight(100)
        layout.addWidget(self.yurt_info)

        self.dev_info = QLabel("""
            <b>Geliştirici</b><br>
            Mustafa AKBAL<br>
            E-posta: <a href='mailto:mstf.akbal@gmail.com' style='color:#F1C40F;'>mstf.akbal@gmail.com</a><br>
            Instagram: <a href='https://instagram.com/mstf.akbal' style='color:#F1C40F;'>@mstf.akbal</a>
        """)
        self.dev_info.setOpenExternalLinks(True)
        self.dev_info.setStyleSheet("color:#000000; font-size:14px;")
        layout.addWidget(self.dev_info, alignment=Qt.AlignCenter)

        self.progress = QProgressBar()
        self.progress.setRange(0,100)
        self.progress.setFixedHeight(30)
        self.progress.setStyleSheet("""
            QProgressBar { border-radius: 5px; background-color: #555555; }
            QProgressBar::chunk { background-color: #F1C40F; }
        """)
        layout.addWidget(self.progress)

        self.cont = QPushButton("Başla")
        self.cont.setFixedWidth(200)
        self.cont.setStyleSheet("background:#C0392B; color:white; border-radius:10px; padding:10px; font-size:16px;")
        self.cont.clicked.connect(self.finish_now)
        layout.addWidget(self.cont, alignment=Qt.AlignCenter)

        self._val = 0
        self.timer = QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    def _tick(self):
        self._val += 2
        if self._val > 100:
            self.finish_now()
            return
        self.progress.setValue(self._val)

    def finish_now(self):
        if self.timer.isActive():
            self.timer.stop()
        self.finished.emit()
        self.close()

    def paintEvent(self, ev):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        r = self.rect()
        grad = QtGui.QLinearGradient(r.topLeft(), r.bottomRight())
        grad.setColorAt(0, QtGui.QColor("#C0392B"))
        grad.setColorAt(1, QtGui.QColor("#F1C40F"))
        painter.setBrush(grad)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(r, 20, 20)

# Custom Notification Dialog
class NotificationDialog(QDialog):
    def __init__(self, parent=None, message="", task_id=None, patient_photo=None):
        super().__init__(parent)
        font_size = parent.settings.get("font_size", 14) if parent else 14
        self.task_id = task_id
        duration = parent.settings.get("notification_duration", 10) if parent else 10
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(450, 250)
        self.setStyleSheet(f"""
            QDialog {{
                background: transparent;
                font-size: {font_size}px;
            }}
        """)
        main_widget = QWidget(self)
        main_widget.setGeometry(0, 0, 450, 250)
        main_widget.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(x1:0 y1:0 x2:1 y2:1, stop:0 #C0392B, stop:1 #F1C40F);
                border-radius: 15px;
                border: 2px solid #FFFFFF;
            }}
        """)
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        photo_label = QLabel()
        photo_label.setFixedSize(100, 100)
        if patient_photo:
            pixmap = QPixmap()
            pixmap.loadFromData(patient_photo)
            photo_label.setPixmap(pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            if os.path.exists(DEFAULT_PATIENT_PHOTO_PATH):
                photo_label.setPixmap(QPixmap(DEFAULT_PATIENT_PHOTO_PATH).scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                photo_label.setText("Foto\nYok")
                photo_label.setAlignment(Qt.AlignCenter)
                photo_label.setStyleSheet(f"background:white; border:2px solid #C0392B; font-size: {font_size-2}px;")
        layout.addWidget(photo_label, alignment=Qt.AlignCenter)

        label = QLabel(message)
        label.setStyleSheet(f"""
            color: #000000;
            font-family: Helvetica;
            font-size: {font_size}px;
            font-weight: bold;
        """)
        label.setWordWrap(True)
        layout.addWidget(label, alignment=Qt.AlignCenter)

        dismiss_btn = QPushButton("Kapat")
        dismiss_btn.setStyleSheet(f"""
            QPushButton {{
                background: #333333;
                color: white;
                border-radius: 8px;
                padding: 8px;
                font-family: Helvetica;
                font-size: {font_size}px;
            }}
            QPushButton:hover {{
                background: #555555;
            }}
        """)
        dismiss_btn.setFixedWidth(120)
        dismiss_btn.clicked.connect(self.accept)
        layout.addWidget(dismiss_btn, alignment=Qt.AlignCenter)

        self.timer = QTimer(self)
        self.timer.setInterval(duration * 1000)
        self.timer.timeout.connect(self.accept)
        self.timer.start()

    def showEvent(self, event):
        # Center the dialog on the screen
        screen = QApplication.primaryScreen().geometry()
        size = self.geometry()
        self.move((screen.width() - size.width()) // 2, (screen.height() - size.height()) // 2)
        super().showEvent(event)

    def accept(self):
        self.timer.stop()
        super().accept()

# Dialogs
class PatientEditDialog(QDialog):
    def __init__(self, parent=None, patient=None):
        super().__init__(parent)
        self.patient = patient
        self.setWindowTitle("Hasta Düzenle" if patient else "Yeni Hasta")
        self.setup_ui()
        if patient:
            self.load_patient(patient)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.room = QLineEdit()
        self.name = QLineEdit()
        self.surname = QLineEdit()
        self.notes = QTextEdit()
        self.tc = QLineEdit()
        self.birth = QDateEdit()
        self.birth.setCalendarPopup(True)
        self.birth.setDisplayFormat("dd/MM/yyyy")
        self.birth.setStyleSheet("""
            QDateEdit { border: 1px solid #C0392B; border-radius: 5px; padding: 5px; background: white; color: #000000; }
            QDateEdit::drop-down { image: url(data/calendar.png); }
        """)
        self.phone = QLineEdit()
        self.photo_btn = QPushButton("Fotoğraf Seç")
        self.photo_btn.clicked.connect(self.pick_photo)
        self.photo_data = None

        form.addRow("Oda No*", self.room)
        form.addRow("Ad*", self.name)
        form.addRow("Soyad*", self.surname)
        form.addRow("Notlar", self.notes)
        form.addRow("T.C. No", self.tc)
        form.addRow("Doğum Tarihi", self.birth)
        form.addRow("Telefon", self.phone)
        form.addRow("Fotoğraf", self.photo_btn)
        layout.addLayout(form)

        btns = QHBoxLayout()
        save = QPushButton("Kaydet")
        cancel = QPushButton("İptal")
        save.clicked.connect(self.save)
        cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(save)
        btns.addWidget(cancel)
        layout.addLayout(btns)

    def pick_photo(self):
        p, _ = QFileDialog.getOpenFileName(self, "Fotoğraf Seç", "", "Images (*.png *.jpg *.jpeg)")
        if p:
            with open(p, "rb") as f:
                self.photo_data = f.read()

    def load_patient(self, row):
        self.room.setText(row["room_number"])
        self.room.setReadOnly(True)
        self.name.setText(row["name"] or "")
        self.surname.setText(row["surname"] or "")
        self.notes.setPlainText(row["notes"] or "")
        self.tc.setText(row["tc_no"] or "")
        if row["birth_date"]:
            try:
                d = datetime.strptime(row["birth_date"], "%Y-%m-%d").date()
                self.birth.setDate(d)
            except:
                pass
        self.phone.setText(row["phone"] or "")
        self.photo_data = row["photo"]

    def save(self):
        room = self.room.text().strip()
        name = self.name.text().strip()
        surname = self.surname.text().strip()
        if not room or not name or not surname:
            QMessageBox.warning(self, "Hata", "Oda, ad ve soyad zorunlu.")
            return
        tc = self.tc.text().strip()
        if tc and (not tc.isdigit() or len(tc) != 11):
            QMessageBox.warning(self, "Hata", "T.C. 11 rakam olmalı.")
            return
        birth = self.birth.date().toString("yyyy-MM-dd")
        conn = get_conn()
        cur = conn.cursor()
        try:
            if self.patient:
                cur.execute("""UPDATE patients SET name=?, surname=?, notes=?, photo=?, tc_no=?, birth_date=?, phone=? WHERE room_number=?""",
                           (name, surname, self.notes.toPlainText(), self.photo_data, tc, birth, self.phone.text().strip(), room))
            else:
                cur.execute("SELECT 1 FROM patients WHERE room_number=?", (room,))
                if cur.fetchone():
                    QMessageBox.warning(self, "Hata", "Aynı oda numarası var.")
                    conn.close()
                    return
                cur.execute("""INSERT INTO patients (room_number, name, surname, notes, photo, tc_no, birth_date, phone) VALUES (?,?,?,?,?,?,?,?)""",
                           (room, name, surname, self.notes.toPlainText(), self.photo_data, tc, birth, self.phone.text().strip()))
            conn.commit()
            conn.close()
            self.accept()
        except Exception as e:
            conn.rollback()
            conn.close()
            QMessageBox.critical(self, "DB Hata", str(e))

class TaskEditDialog(QDialog):
    def __init__(self, parent=None, task=None, default_room=None):
        super().__init__(parent)
        self.task = task
        self.default_room = default_room
        font_size = parent.settings.get("font_size", 14) if parent else 14
        self.setWindowTitle("Görev Düzenle" if task else "Yeni Görev")
        self.setStyleSheet(f"""
            QDialog {{
                background: #333333;
                color: white;
                font-family: Helvetica;
                font-size: {font_size}px;
            }}
        """)
        self.setup_ui()
        if task:
            self.load_task(task)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(12)
        form.setContentsMargins(10, 10, 10, 10)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        font_size = self.parent().settings.get("font_size", 14) if self.parent() else 14
        self.patient_combo = QComboBox()
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT room_number, name, surname FROM patients ORDER BY room_number")
        patients = cur.fetchall()
        conn.close()
        for r in patients:
            self.patient_combo.addItem(f"{r['room_number']} - {r['name']} {r['surname']}", r['room_number'])
        if self.default_room:
            idx = self.patient_combo.findData(self.default_room)
            if idx >= 0:
                self.patient_combo.setCurrentIndex(idx)
        self.patient_combo.setStyleSheet(f"""
            QComboBox {{
                border: 4px solid #C0392B;
                border-radius: 5px;
                padding: 5px;
                background: white;
                color: #000000;
                font-family: Helvetica;
                font-size: {font_size}px;
            }}
        """)
        self.patient_combo.setMinimumHeight(30)
        form.addRow("Hasta*", self.patient_combo)

        self.task_edit = QLineEdit()
        self.task_edit.setStyleSheet(f"""
            QLineEdit {{
                border: 4px solid #C0392B;
                border-radius: 5px;
                padding: 5px;
                background: white;
                color: #000000;
                font-family: Helvetica;
                font-size: {font_size}px;
            }}
        """)
        self.task_edit.setMinimumHeight(30)
        form.addRow("Görev*", self.task_edit)

        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setStyleSheet(f"""
            QTimeEdit {{
                border: 4px solid #C0392B;
                border-radius: 5px;
                padding: 5px;
                background: white;
                color: #000000;
                font-family: Helvetica;
                font-size: {font_size}px;
            }}
            QTimeEdit::drop-down {{ image: url(data/clock.png); }}
        """)
        self.time_edit.setMinimumHeight(30)
        form.addRow("Saat", self.time_edit)

        self.time_type = QComboBox()
        self.time_type.addItems(["Saat Belirt", "Gün İçinde", "Akşam"])
        self.time_type.setStyleSheet(f"""
            QComboBox {{
                border: 4px solid #C0392B;
                border-radius: 5px;
                padding: 5px;
                background: white;
                color: #000000;
                font-family: Helvetica;
                font-size: {font_size}px;
            }}
        """)
        self.time_type.setMinimumHeight(30)
        form.addRow("Zaman Türü", self.time_type)

        self.time_type.currentIndexChanged.connect(self.toggle_time_edit)

        self.repeat = QComboBox()
        self.repeat.addItems(["Yok", "Her Gün", "Tek Günler", "Çift Günler", "Haftanın Günleri", "Kaç Günde Bir"])
        self.repeat.setStyleSheet(f"""
            QComboBox {{
                border: 4px solid #C0392B;
                border-radius: 5px;
                padding: 5px;
                background: white;
                color: #000000;
                font-family: Helvetica;
                font-size: {font_size}px;
            }}
        """)
        self.repeat.setMinimumHeight(30)
        form.addRow("Tekrar Türü", self.repeat)

        self.weekdays_box = QWidget()
        wd_layout = QHBoxLayout(self.weekdays_box)
        self.week_checks = []
        days = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
        for i, d in enumerate(days):
            cb = QCheckBox(d)
            cb.setStyleSheet(f"color: white; font-family: Helvetica; font-size: {font_size}px;")
            self.week_checks.append(cb)
            wd_layout.addWidget(cb)
        self.weekdays_box.setVisible(False)
        form.addRow("Haftanın Günleri", self.weekdays_box)

        self.repeat_interval = QSpinBox()
        self.repeat_interval.setRange(1, 365)
        self.repeat_interval.setValue(1)
        self.repeat_interval.setStyleSheet(f"""
            QSpinBox {{
                border: 4px solid #C0392B;
                border-radius: 5px;
                padding: 5px;
                background: white;
                color: #000000;
                font-family: Helvetica;
                font-size: {font_size}px;
            }}
        """)
        self.repeat_interval.setMinimumHeight(30)
        self.repeat_interval.setVisible(False)
        form.addRow("Kaç Günde Bir", self.repeat_interval)

        self.repeat.currentIndexChanged.connect(self.toggle_repeat_options)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setDate(QtCore.QDate.currentDate())
        self.date_edit.setStyleSheet(f"""
            QDateEdit {{
                border: 4px solid #C0392B;
                border-radius: 5px;
                padding: 5px;
                background: white;
                color: #000000;
                font-family: Helvetica;
                font-size: {font_size}px;
            }}
            QDateEdit::drop-down {{ image: url(data/calendar.png); }}
        """)
        self.date_edit.setMinimumHeight(30)
        form.addRow("Başlangıç Tarihi", self.date_edit)

        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat("dd/MM/yyyy")
        self.end_date_edit.setDate(QtCore.QDate.currentDate())
        self.end_date_edit.setStyleSheet(f"""
            QDateEdit {{
                border: 4px solid #C0392B;
                border-radius: 5px;
                padding: 5px;
                background: white;
                color: #000000;
                font-family: Helvetica;
                font-size: {font_size}px;
            }}
            QDateEdit::drop-down {{ image: url(data/calendar.png); }}
        """)
        self.end_date_edit.setMinimumHeight(30)
        self.end_date_edit.setVisible(False)
        self.use_end_date = QCheckBox("Bitiş Tarihi Kullan")
        self.use_end_date.setStyleSheet(f"color: white; font-family: Helvetica; font-size: {font_size}px;")
        self.use_end_date.stateChanged.connect(self.toggle_end_date)
        form.addRow(self.use_end_date)
        form.addRow("Bitiş Tarihi", self.end_date_edit)

        layout.addLayout(form)

        btns = QHBoxLayout()
        save = QPushButton("Kaydet")
        save.setStyleSheet(f"""
            QPushButton {{
                background: #C0392B;
                color: white;
                border-radius: 5px;
                padding: 5px;
                font-family: Helvetica;
                font-size: {font_size}px;
            }}
        """)
        cancel = QPushButton("İptal")
        cancel.setStyleSheet(f"""
            QPushButton {{
                background: #C0392B;
                color: white;
                border-radius: 5px;
                padding: 5px;
                font-family: Helvetica;
                font-size: {font_size}px;
            }}
        """)
        save.clicked.connect(self.save)
        cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(save)
        btns.addWidget(cancel)
        layout.addLayout(btns)

        self.toggle_time_edit()
        self.setMinimumSize(500, 600)

    def toggle_time_edit(self):
        """Enable or disable time_edit based on time_type selection."""
        time_type = self.time_type.currentText()
        self.time_edit.setEnabled(time_type == "Saat Belirt")

    def toggle_repeat_options(self):
        repeat_type = self.repeat.currentText()
        self.weekdays_box.setVisible(repeat_type == "Haftanın Günleri")
        self.repeat_interval.setVisible(repeat_type == "Kaç Günde Bir")

    def toggle_end_date(self):
        self.end_date_edit.setVisible(self.use_end_date.isChecked())

    def load_task(self, row):
        idx = self.patient_combo.findData(row["room_number"])
        if idx >= 0:
            self.patient_combo.setCurrentIndex(idx)
        self.task_edit.setText(row["task"] or "")
        if row["time"]:
            try:
                hh, mm = map(int, row["time"].split(":"))
                self.time_edit.setTime(QtCore.QTime(hh, mm))
            except:
                pass
        if row["time_type"]:
            i = self.time_type.findText(row["time_type"])
            if i >= 0:
                self.time_type.setCurrentIndex(i)
        if row["repeat_type"]:
            i = self.repeat.findText(row["repeat_type"])
            if i >= 0:
                self.repeat.setCurrentIndex(i)
        if row["repeat_days"]:
            days = row["repeat_days"].split(",")
            for d in days:
                try:
                    di = int(d)
                    self.week_checks[di].setChecked(True)
                except:
                    pass
        if row["repeat_interval"]:
            self.repeat_interval.setValue(row["repeat_interval"])
        if row["date"]:
            try:
                d = datetime.strptime(row["date"], "%Y-%m-%d").date()
                self.date_edit.setDate(d)
            except:
                pass
        if row["end_date"]:
            try:
                d = datetime.strptime(row["end_date"], "%Y-%m-%d").date()
                self.end_date_edit.setDate(d)
                self.use_end_date.setChecked(True)
            except:
                pass
        # Ensure time_edit and repeat options are correctly set
        self.toggle_time_edit()
        self.toggle_repeat_options()
        self.toggle_end_date()

    def save(self):
        room = self.patient_combo.currentData()
        tasktxt = self.task_edit.text().strip()
        if not room or not tasktxt:
            QMessageBox.warning(self, "Hata", "Hasta ve görev zorunlu.")
            return
        time_str = self.time_edit.time().toString("HH:mm") if self.time_type.currentText() == "Saat Belirt" else ""
        time_type = self.time_type.currentText()
        repeat_type = self.repeat.currentText()
        repeat_days = ""
        repeat_interval = None
        if repeat_type == "Haftanın Günleri":
            sel = [str(i) for i, cb in enumerate(self.week_checks) if cb.isChecked()]
            if not sel:
                QMessageBox.warning(self, "Hata", "En az bir hafta günü seçin.")
                return
            repeat_days = ",".join(sel)
        elif repeat_type == "Kaç Günde Bir":
            repeat_interval = self.repeat_interval.value()
        date_str = self.date_edit.date().toString("yyyy-MM-dd")
        end_date_str = self.end_date_edit.date().toString("yyyy-MM-dd") if self.use_end_date.isChecked() else ""
        conn = get_conn()
        cur = conn.cursor()
        try:
            if self.task:
                cur.execute(
                    """UPDATE tasks SET room_number=?, task=?, time=?, time_type=?, repeat_type=?, date=?, end_date=?, repeat_days=?, repeat_interval=?, notified=0 WHERE id=?""",
                    (room, tasktxt, time_str, time_type, repeat_type, date_str, end_date_str, repeat_days, repeat_interval, self.task["id"])
                )
            else:
                cur.execute(
                    """INSERT INTO tasks (room_number, task, time, done, repeat_type, time_type, date, end_date, cancelled, repeat_days, repeat_interval, notified, completed_time)
                    VALUES (?,?,?,?,?,?,?,?,0,?,?,0,NULL)""",
                    (room, tasktxt, time_str, 0, repeat_type, time_type, date_str, end_date_str, repeat_days, repeat_interval)
                )
            conn.commit()
            conn.close()
            self.accept()
        except Exception as e:
            conn.rollback()
            conn.close()
            QMessageBox.critical(self, "DB Hata", str(e))

class TaskListDialog(QDialog):
    def __init__(self, parent=None, tasks=None, title="Görevler"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(800, 400)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Hasta", "Görev", "Saat", "Zaman Türü"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table)
        btn = QPushButton("Kapat")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn, alignment=Qt.AlignRight)
        if tasks:
            self.load_tasks(tasks)

    def load_tasks(self, tasks):
        self.table.setRowCount(0)
        for t in tasks:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(t.get("patient", "")))
            self.table.setItem(r, 1, QTableWidgetItem(t.get("task", "")))
            self.table.setItem(r, 2, QTableWidgetItem(t.get("time", "")))
            self.table.setItem(r, 3, QTableWidgetItem(t.get("time_type", "")))

# Main Window
class PatientTaskApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.setWindowTitle("Galatasaraylılar Yurdu Huzur Evi - Hasta Görev Yönetim Sistemi")
        self.showMaximized()

        central = QWidget()
        self.setCentralWidget(central)
        main = QVBoxLayout(central)
        main.setSpacing(6)

        top_bar = QWidget()
        top_bar.setFixedHeight(120)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(10, 6, 10, 6)
        self.left_area = QLabel("")
        self.center_clock = QLabel()
        self.center_clock.setAlignment(Qt.AlignCenter)
        self.center_clock.setStyleSheet("""
            background: qlineargradient(x1:0 y1:0 x2:1 y2:1, stop:0 #C0392B, stop:1 #F1C40F);
            color: #000000;
            border-radius: 15px;
            padding: 15px;
            font-family: Helvetica;
        """)
        self.right_area = QWidget()
        right_layout = QHBoxLayout(self.right_area)
        self.refresh_btn = QPushButton("Yenile")
        self.refresh_btn.clicked.connect(self.refresh_all)
        right_layout.addWidget(self.refresh_btn)
        top_layout.addWidget(self.left_area, 1)
        top_layout.addWidget(self.center_clock, 3)
        top_layout.addWidget(self.right_area, 1)
        main.addWidget(top_bar)

        self.tabs = QTabWidget()
        main.addWidget(self.tabs)
        self.build_tasks_tab()
        self.build_patients_tab()
        self.build_task_mgmt_tab()
        self.build_calendar_tab()
        self.build_archive_tab()
        self.build_yurt_info_tab()
        self.build_developer_tab()
        self.build_settings_tab()

        self.apply_theme(self.settings.get("theme", "Galatasaray"))
        self.apply_font_size(self.settings.get("font_size", 14))

        self.tasks_cache = []
        self.last_cache_date = None

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(1000)
        self.flash_timer = QTimer(self)
        self.flash_timer.timeout.connect(self.update_flashing)
        self.flash_timer.start(1000)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_all)
        self.refresh_timer.start(60*1000)
        self.notify_timer = QTimer(self)
        self.notify_timer.timeout.connect(self.check_notifications)
        self.notify_timer.start(30*1000)
        self.flash_state = False

        self.refresh_all()

    def parse_time(self, time_str):
        if not time_str:
            return time(8, 0)
        try:
            hh, mm = map(int, time_str.split(":"))
            return time(hh, mm)
        except:
            return time(8, 0)

    def build_tasks_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        stats = QHBoxLayout()
        self.total_btn = QPushButton("Toplam: 0")
        self.done_btn = QPushButton("Tamamlanmış: 0")
        self.wait_btn = QPushButton("Vakti Gelen: 0")
        self.upcoming_btn = QPushButton("Gelecek: (0)")
        self.cancel_btn = QPushButton("İptal: 0")
        for b in (self.total_btn, self.done_btn, self.wait_btn, self.upcoming_btn, self.cancel_btn):
            b.setFlat(True)
        self.total_btn.clicked.connect(lambda: self.show_task_list("all"))
        self.done_btn.clicked.connect(lambda: self.show_task_list("done"))
        self.wait_btn.clicked.connect(lambda: self.show_task_list("waiting"))
        self.upcoming_btn.clicked.connect(lambda: self.show_task_list("upcoming"))
        self.cancel_btn.clicked.connect(lambda: self.show_task_list("cancelled"))
        stats.addWidget(self.total_btn)
        stats.addWidget(self.done_btn)
        stats.addWidget(self.wait_btn)
        stats.addWidget(self.upcoming_btn)
        stats.addWidget(self.cancel_btn)
        stats.addStretch()
        layout.addLayout(stats)

        self.tasks_subtab = QTabWidget()
        # Daytime tab
        self.day_widget = QWidget()
        day_layout = QVBoxLayout(self.day_widget)
        self.day_scroll = QScrollArea()
        self.day_scroll.setWidgetResizable(True)
        self.day_container = QWidget()
        self.day_v = QVBoxLayout(self.day_container)
        self.day_v.setAlignment(Qt.AlignCenter)
        self.day_scroll.setWidget(self.day_container)
        day_layout.addWidget(self.day_scroll)
        self.tasks_subtab.addTab(self.day_widget, "Gündüz Vardiyası (08:00-20:00)")

        # Night tab
        self.night_widget = QWidget()
        night_layout = QVBoxLayout(self.night_widget)
        self.night_scroll = QScrollArea()
        self.night_scroll.setWidgetResizable(True)
        self.night_container = QWidget()
        self.night_v = QVBoxLayout(self.night_container)
        self.night_v.setAlignment(Qt.AlignCenter)
        self.night_scroll.setWidget(self.night_container)
        night_layout.addWidget(self.night_scroll)
        self.tasks_subtab.addTab(self.night_widget, "Akşam Gece Vardiyası (20:00-08:00)")

        layout.addWidget(self.tasks_subtab)
        self.tabs.addTab(w, "Görevler")

    def build_patients_tab(self):
        w = QWidget()
        l = QVBoxLayout(w)
        top = QHBoxLayout()
        self.patient_selector = QComboBox()
        self.patient_selector.currentIndexChanged.connect(self.update_selected_patient)
        top.addWidget(QLabel("Hasta Seç:"))
        top.addWidget(self.patient_selector)
        add_patient_btn = QPushButton("Yeni Hasta Ekle")
        add_patient_btn.clicked.connect(self.add_patient)
        top.addWidget(add_patient_btn)
        add_task_btn = QPushButton("Yeni Görev Ekle")
        add_task_btn.clicked.connect(self.add_task_for_selected_patient)
        top.addWidget(add_task_btn)
        delete_patient_btn = QPushButton("Hastayı Sil")
        delete_patient_btn.clicked.connect(self.delete_selected_patient)
        top.addWidget(delete_patient_btn)
        top.addStretch()
        l.addLayout(top)
        body = QHBoxLayout()
        self.photo = QLabel("Fotoğraf yok")
        self.photo.setFixedSize(150, 150)
        self.photo.setStyleSheet("""
            border: 2px solid #F1C40F;
            background: #fff;
            border-radius: 10px;
        """)
        body.addWidget(self.photo)
        details = QVBoxLayout()
        self.patient_details = QTextEdit()
        self.patient_details.setReadOnly(True)
        self.patient_details.setStyleSheet("""
            background: rgba(255,255,255,0.1);
            border: 1px solid #C0392B;
            border-radius: 10px;
            padding: 10px;
        """)
        self.patient_details.setFixedWidth(350)
        details.addWidget(self.patient_details)
        edit_patient_btn = QPushButton("Hastayı Düzenle")
        edit_patient_btn.clicked.connect(self.edit_selected_patient)
        details.addWidget(edit_patient_btn)
        body.addLayout(details)
        self.patient_task_table = QTableWidget(0, 8)
        self.patient_task_table.setHorizontalHeaderLabels(["Görev", "Saat", "Durum", "Tekrar", "Zaman Türü", "Düzenle", "Arşivle", "Sil"])
        self.patient_task_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.patient_task_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        body.addWidget(self.patient_task_table)
        l.addLayout(body)
        self.tabs.addTab(w, "Hastalar")

    def build_task_mgmt_tab(self):
        w = QWidget()
        l = QVBoxLayout(w)
        self.tasks_table = QTableWidget(0, 9)
        self.tasks_table.setHorizontalHeaderLabels(["Hasta", "Görev", "Saat", "Durum", "Tekrar", "Zaman Türü", "Düzenle", "Sil", "Arşivle"])
        self.tasks_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tasks_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        l.addWidget(self.tasks_table)
        self.tabs.addTab(w, "Görev Yönetimi")

    def build_calendar_tab(self):
        w = QWidget()
        l = QVBoxLayout(w)
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.setLocale(QLocale(QLocale.Turkish, QLocale.Turkey))
        self.calendar.selectionChanged.connect(self.reload_calendar_tasks)
        l.addWidget(self.calendar)
        self.calendar_table = QTableWidget(0, 6)
        self.calendar_table.setHorizontalHeaderLabels(["Hasta", "Görev", "Saat", "Durum", "Tekrar", "Zaman Türü"])
        self.calendar_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.calendar_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        l.addWidget(self.calendar_table)
        self.tabs.addTab(w, "Takvim")

    def build_archive_tab(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(QLabel("Arşivlenmiş Hastalar"))
        self.archive_patients = QTableWidget(0, 6)
        self.archive_patients.setHorizontalHeaderLabels(["Oda", "Ad", "Soyad", "T.C.", "Geri Yükle", "Sil"])
        self.archive_patients.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.archive_patients.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        l.addWidget(self.archive_patients)
        l.addWidget(QLabel("Arşivlenmiş Görevler"))
        self.archive_tasks = QTableWidget(0, 7)
        self.archive_tasks.setHorizontalHeaderLabels(["Hasta", "Görev", "Saat", "Tarih", "Zaman Türü", "Geri Yükle", "Sil"])
        self.archive_tasks.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.archive_tasks.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        l.addWidget(self.archive_tasks)
        self.tabs.addTab(w, "Arşiv")

    def build_yurt_info_tab(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setSpacing(20)
        header = QWidget()
        header_layout = QHBoxLayout(header)
        logo = QLabel()
        logo.setFixedSize(120, 120)
        if os.path.exists(LOGO_PATH):
            logo.setPixmap(QPixmap(LOGO_PATH).scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            logo.setText("LOGO")
            logo.setAlignment(Qt.AlignCenter)
            logo.setStyleSheet("background:white; border:4px solid #F1C40F; font-size:16px;")
        header_layout.addWidget(logo)
        title = QLabel("Galatasaraylılar Yurdu Huzur Evi")
        title.setFont(QFont("Helvetica", 24, QFont.Bold))
        title.setStyleSheet("color: #000000; padding: 10px;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        l.addWidget(header)

        desc = QTextEdit()
        desc.setReadOnly(True)
        desc.setHtml("""
            <div style='text-align: justify; padding: 15px;'>
                <h2 style='color: #F1C40F;'>Hakkımızda</h2>
                <p>Galatasaraylılar Yurdu Huzurevi ve Yaşlı Bakım Merkezi, 500 yılı aşkın tarihiyle bir eğitim, kültür, sanat ve spor ocağı olan Galatasaray Lisesi’nden kaynaklanan kuruluşlardan biri olan Galatasaraylılar Yardımlaşma Vakfı tarafından 1977 yılında kurulmuştur.</p>
                <p>Florya’nın en güzel köşelerinden birinde, 5000 m² alana inşa edilmiş olan yurdumuz, otel konforunda tek kişilik odalar ve ferah ortak alanlarla hizmet vermektedir. “Geçmişimiz de geleceğimiz de Galatasaray” felsefesiyle, sevgi, bağlılık ve dayanışma ruhunu yaşatmayı hedefliyoruz.</p>
                <p><b>Misyonumuz:</b> Büyüklerimizin yaşamlarını huzur, güven, sağlık ve mutluluk içinde sürdürmelerini sağlamak, ikinci baharlarını pilav günü ruhuyla yaşamalarına olanak tanımaktır.</p>
                <p><b>Vizyonumuz:</b> Galatasaray’ın temel değer ve ilkeleri çerçevesinde, yaşlı bakımında öncü bir kurum olarak, misafirlerimize en yüksek yaşam kalitesini sunmak.</p>
            </div>
        """)
        desc.setStyleSheet("""
            background: rgba(255,255,255,0.1);
            border: none;
            border-radius: 10px;
            padding: 10px;
        """)
        l.addWidget(desc)

        contact = QWidget()
        contact_layout = QVBoxLayout(contact)
        contact_title = QLabel("İletişim Bilgileri")
        contact_title.setFont(QFont("Helvetica", 16, QFont.Bold))
        contact_title.setStyleSheet("color: #F1C40F; padding: 5px;")
        contact_layout.addWidget(contact_title)
        contact_info = QLabel("""
            <p style='line-height: 1.6;'>
                <b>Telefon:</b> (0212) 574 52 55<br>
                <b>Mobil:</b> (0532) 448 21 55<br>
                <b>E-posta:</b> <a href='mailto:bilgi@gsyardimlasmavakfi.org'>bilgi@gsyardimlasmavakfi.org</a><br>
                <b>Yönetim:</b> <a href='mailto:yonetim@gsyardimlasmavakfi.org'>yonetim@gsyardimlasmavakfi.org</a><br>
                <b>Adres:</b> Şenlikköy Mh. Orman Sk. No:39/1 Florya Bakırköy/İstanbul
            </p>
        """)
        contact_info.setOpenExternalLinks(True)
        contact_info.setStyleSheet("")
        contact_layout.addWidget(contact_info)
        l.addWidget(contact)
        l.addStretch()
        self.tabs.addTab(w, "Yurt Hakkında")

    def build_developer_tab(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setSpacing(20)
        l.setContentsMargins(20, 20, 20, 20)
        l.setAlignment(Qt.AlignCenter)

        card = QWidget()
        card.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0 y1:0 x2:1 y2:1, stop:0 #C0392B, stop:1 #F1C40F);
                border-radius: 15px;
                border: 2px solid #FFFFFF;
                padding: 20px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(15)
        card_layout.setAlignment(Qt.AlignCenter)

        photo = QLabel()
        photo.setFixedSize(170, 170)
        if os.path.exists(DEVELOPER_PHOTO_PATH):
            pixmap = QPixmap(DEVELOPER_PHOTO_PATH)
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(120, 120, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                circular_pixmap = QPixmap(120, 120)
                circular_pixmap.fill(Qt.transparent)
                painter = QtGui.QPainter(circular_pixmap)
                painter.setRenderHint(QtGui.QPainter.Antialiasing)
                path = QtGui.QPainterPath()
                path.addEllipse(0, 0, 120, 120)
                painter.setClipPath(path)
                offset_x = (120 - scaled_pixmap.width()) // 2
                offset_y = (120 - scaled_pixmap.height()) // 2
                painter.drawPixmap(offset_x, offset_y, scaled_pixmap)
                painter.end()
                photo.setPixmap(circular_pixmap)
                photo.setStyleSheet("border: 3px solid #F1C40F; border-radius: 60px;")
            else:
                photo.setText("MA")
                photo.setAlignment(Qt.AlignCenter)
                photo.setStyleSheet("""
                    background: #F1C40F;
                    border: 3px solid #C0392B;
                    border-radius: 60px;
                    color: #C0392B;
                    font-size: 40px;
                    font-weight: bold;
                """)
        else:
            photo.setText("MA")
            photo.setAlignment(Qt.AlignCenter)
            photo.setStyleSheet("""
                background: #F1C40F;
                border: 3px solid #C0392B;
                border-radius: 60px;
                color: #C0392B;
                font-size: 40px;
                font-weight: bold;
            """)
        card_layout.addWidget(photo)

        title = QLabel("Geliştirici")
        title.setFont(QFont("Helvetica", 28, QFont.Bold))
        title.setStyleSheet("color: #000000; margin-bottom: 10px;")
        card_layout.addWidget(title)

        dev_info = QLabel("""
            <div style='text-align: center; line-height: 1.8;'>
                <h2 style='color: #F1C40F; font-size: 24px; margin: 0;'>Mustafa AKBAL</h2>
                <p style='font-size: 16px; color: #000000;'>
                    <b>E-posta:</b> <a href='mailto:mstf.akbal@gmail.com' style='color: #F1C40F; text-decoration: none;'>mstf.akbal@gmail.com</a><br>
                    <b>Telefon:</b> +90 544 748 5959<br>
                    <b>Instagram:</b> <a href='https://instagram.com/mstf.akbal' style='color: #F1C40F; text-decoration: none;'>@mstf.akbal</a><br><br>
                    Bu sistem, Galatasaraylılar Yurdu'nun ihtiyaçlarına özel olarak tasarlandı. Kullanıcı dostu arayüz ve güvenilir veritabanı yönetimi ile bakım süreçlerini kolaylaştırmayı hedefliyorum.
                </p>
            </div>
        """)
        dev_info.setOpenExternalLinks(True)
        dev_info.setStyleSheet("font-family: Helvetica; font-size: 16px;")
        dev_info.setTextInteractionFlags(Qt.TextBrowserInteraction)
        card_layout.addWidget(dev_info)

        contact_btn = QPushButton("İletişime Geç")
        contact_btn.setStyleSheet("""
            QPushButton {
                background: #C0392B;
                color: white;
                border-radius: 10px;
                padding: 10px;
                font-family: Helvetica;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #A93226;
            }
        """)
        contact_btn.setFixedWidth(200)
        contact_btn.clicked.connect(lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl("mailto:mstf.akbal@gmail.com")))
        card_layout.addWidget(contact_btn, alignment=Qt.AlignCenter)

        copyright_label = QLabel("© 2025 Mustafa AKBAL. Tüm Hakları Saklıdır.")
        copyright_label.setStyleSheet("""
            color: #000000;
            font-family: Helvetica;
            font-size: 14px;
            font-style: italic;
            margin-top: 10px;
        """)
        card_layout.addWidget(copyright_label, alignment=Qt.AlignCenter)

        l.addStretch()
        l.addWidget(card)
        l.addStretch()
        self.tabs.addTab(w, "Geliştirici")

    def build_settings_tab(self):
        w = QWidget()
        l = QFormLayout(w)
        font_size = self.settings.get("font_size", 14)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Galatasaray", "Koyu"])
        self.theme_combo.setCurrentText(self.settings.get("theme", "Galatasaray"))
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)
        l.addRow("Tema", self.theme_combo)

        self.font_slider = QSlider(Qt.Horizontal)
        self.font_slider.setRange(10, 22)
        self.font_slider.setValue(self.settings.get("font_size", 14))
        self.font_slider.valueChanged.connect(self.on_font_changed)
        l.addRow("Yazı Boyutu", self.font_slider)

        self.notify_check = QCheckBox("Bildirimleri Etkinleştir")
        self.notify_check.setChecked(self.settings.get("notifications_enabled", True))
        self.notify_check.stateChanged.connect(self.on_notify_changed)
        l.addRow(self.notify_check)

        self.timeout_combo = QComboBox()
        self.timeout_combo.addItems([str(i) for i in range(1, 25)])
        self.timeout_combo.setCurrentText(str(self.settings.get("completed_task_timeout", 4)))
        self.timeout_combo.currentIndexChanged.connect(self.on_timeout_changed)
        l.addRow("Tamamlanmış Görev Görünürlük Süresi (saat)", self.timeout_combo)

        self.clock_format = QComboBox()
        self.clock_format.addItems(["24 Saat", "12 Saat"])
        self.clock_format.setCurrentText(self.settings.get("clock_format", "24 Saat"))
        self.clock_format.currentIndexChanged.connect(self.on_clock_format_changed)
        l.addRow("Saat Formatı", self.clock_format)

        self.auto_refresh = QCheckBox("Otomatik Yenileme")
        self.auto_refresh.setChecked(self.settings.get("auto_refresh", True))
        self.auto_refresh.stateChanged.connect(self.on_auto_refresh_changed)
        l.addRow("Tablo Otomatik Yenileme", self.auto_refresh)

        self.notification_duration_spin = QSpinBox()
        self.notification_duration_spin.setRange(5, 60)
        self.notification_duration_spin.setValue(self.settings.get("notification_duration", 10))
        self.notification_duration_spin.valueChanged.connect(self.on_notification_duration_changed)
        l.addRow("Bildirim Süresi (saniye)", self.notification_duration_spin)

        # Vardiya saatleri
        self.day_start_edit = QTimeEdit()
        self.day_start_edit.setDisplayFormat("HH:mm")
        self.day_start_edit.setTime(QtCore.QTime.fromString(self.settings.get("day_start", "08:00"), "HH:mm"))
        self.day_start_edit.timeChanged.connect(self.on_day_start_changed)
        l.addRow("Gündüz Vardiyası Başlangıç", self.day_start_edit)

        self.day_end_edit = QTimeEdit()
        self.day_end_edit.setDisplayFormat("HH:mm")
        self.day_end_edit.setTime(QtCore.QTime.fromString(self.settings.get("day_end", "20:00"), "HH:mm"))
        self.day_end_edit.timeChanged.connect(self.on_day_end_changed)
        l.addRow("Gündüz Vardiyası Bitiş", self.day_end_edit)

        self.night_start_edit = QTimeEdit()
        self.night_start_edit.setDisplayFormat("HH:mm")
        self.night_start_edit.setTime(QtCore.QTime.fromString(self.settings.get("night_start", "20:00"), "HH:mm"))
        self.night_start_edit.timeChanged.connect(self.on_night_start_changed)
        l.addRow("Gece Vardiyası Başlangıç", self.night_start_edit)

        self.night_end_edit = QTimeEdit()
        self.night_end_edit.setDisplayFormat("HH:mm")
        self.night_end_edit.setTime(QtCore.QTime.fromString(self.settings.get("night_end", "08:00"), "HH:mm"))
        self.night_end_edit.timeChanged.connect(self.on_night_end_changed)
        l.addRow("Gece Vardiyası Bitiş", self.night_end_edit)

        self.theme_preview = QLabel("Tema önizlemesi")
        self.theme_preview.setFixedHeight(80)
        l.addRow(self.theme_preview)
        self.update_theme_preview()
        self.tabs.addTab(w, "Ayarlar")

    def refresh_all(self):
        self.reload_patients()
        self.reload_tasks()
        self.reload_archive()
        self.reload_calendar_tasks()
        self.update_task_sections()

    def reload_patients(self):
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM patients ORDER BY room_number")
        rows = cur.fetchall()
        conn.close()
        self.patient_selector.blockSignals(True)
        self.patient_selector.clear()
        self.patient_selector.addItem("Seçiniz", "")
        for r in rows:
            self.patient_selector.addItem(f"{r['room_number']} - {r['name']} {r['surname']}", r['room_number'])
        if rows:
            self.patient_selector.setCurrentIndex(1)
        self.patient_selector.blockSignals(False)
        self.update_selected_patient()

    def add_patient(self):
        dlg = PatientEditDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            self.reload_patients()

    def edit_selected_patient(self):
        room = self.patient_selector.currentData()
        if not room:
            QMessageBox.warning(self, "Hata", "Lütfen bir hasta seçin.")
            return
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM patients WHERE room_number=?", (room,))
        r = cur.fetchone()
        conn.close()
        if r:
            dlg = PatientEditDialog(self, r)
            if dlg.exec_() == QDialog.Accepted:
                self.reload_patients()

    def delete_selected_patient(self):
        room = self.patient_selector.currentData()
        if not room:
            QMessageBox.warning(self, "Hata", "Lütfen bir hasta seçin.")
            return
        if QMessageBox.question(self, "Onay", f"{room} numaralı hasta arşivlenip silinsin mi?") != QMessageBox.Yes:
            return
        self.delete_patient(room)

    def delete_patient(self, room):
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM patients WHERE room_number=?", (room,))
        p = cur.fetchone()
        if p:
            cur.execute(
                "INSERT OR REPLACE INTO archive_patients (room_number,name,surname,notes,photo,tc_no,birth_date,phone) VALUES (?,?,?,?,?,?,?,?)",
                (p["room_number"], p["name"], p["surname"], p["notes"], p["photo"], p["tc_no"], p["birth_date"], p["phone"])
            )
        cur.execute("DELETE FROM patients WHERE room_number=?", (room,))
        cur.execute("SELECT * FROM tasks WHERE room_number=?", (room,))
        for t in cur.fetchall():
            cur.execute(
                "INSERT INTO archive (room_number,task,time,date,end_date,time_type) VALUES (?,?,?,?,?,?)",
                (t["room_number"], t["task"], t["time"], t["date"], t["end_date"], t["time_type"])
            )
        cur.execute("DELETE FROM tasks WHERE room_number=?", (room,))
        conn.commit()
        conn.close()
        self.refresh_all()

    def reload_tasks(self):
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT t.*, p.name, p.surname, p.photo FROM tasks t LEFT JOIN patients p ON p.room_number=t.room_number ORDER BY date, time")
        rows = cur.fetchall()
        conn.close()
        self.tasks_cache = [dict(r) for r in rows]

        self.tasks_table.setRowCount(0)
        for r in self.tasks_cache:
            row = self.tasks_table.rowCount()
            self.tasks_table.insertRow(row)
            name = f"{r['room_number']} - {r['name'] or ''} {r['surname'] or ''}"
            self.tasks_table.setItem(row, 0, QTableWidgetItem(name))
            self.tasks_table.setItem(row, 1, QTableWidgetItem(r["task"]))
            self.tasks_table.setItem(row, 2, QTableWidgetItem(r["time"] or ""))
            self.tasks_table.setItem(row, 3, QTableWidgetItem("Tamamlandı" if r["done"] else ("İptal" if r["cancelled"] else "Aktif")))
            self.tasks_table.setItem(row, 4, QTableWidgetItem(r["repeat_type"] or ""))
            self.tasks_table.setItem(row, 5, QTableWidgetItem(r["time_type"] or ""))
            edit = QPushButton("Düzenle")
            edit.clicked.connect(partial(self.edit_task, r["id"]))
            self.tasks_table.setCellWidget(row, 6, edit)
            delete = QPushButton("Sil")
            delete.clicked.connect(partial(self.delete_task, r["id"]))
            self.tasks_table.setCellWidget(row, 7, delete)
            archive = QPushButton("Arşivle")
            archive.clicked.connect(partial(self.archive_task, r["id"]))
            self.tasks_table.setCellWidget(row, 8, archive)

    def add_task(self):
        dlg = TaskEditDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            self.reload_tasks()
            self.update_task_sections()

    def edit_task(self, task_id):
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
        r = cur.fetchone()
        conn.close()
        if r:
            dlg = TaskEditDialog(self, r)
            if dlg.exec_() == QDialog.Accepted:
                self.reload_tasks()
                self.update_task_sections()
                if self.tabs.currentIndex() == 1 and self.settings.get("auto_refresh", True):
                    self.update_selected_patient()

    def delete_task(self, task_id):
        if QMessageBox.question(self, "Onay", "Görevi kalıcı olarak silmek istiyor musunuz?") != QMessageBox.Yes:
            return
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        conn.commit()
        conn.close()
        self.reload_tasks()
        self.update_task_sections()
        if self.tabs.currentIndex() == 1 and self.settings.get("auto_refresh", True):
            self.update_selected_patient()

    def archive_task(self, task_id):
        if QMessageBox.question(self, "Onay", "Görevi arşivlemek istiyor musunuz?") != QMessageBox.Yes:
            return
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
        t = cur.fetchone()
        if t:
            cur.execute(
                "INSERT INTO archive (room_number,task,time,date,end_date,time_type) VALUES (?,?,?,?,?,?)",
                (t["room_number"], t["task"], t["time"], t["date"], t["end_date"], t["time_type"])
            )
            cur.execute("DELETE FROM tasks WHERE id=?", (task_id,))
            conn.commit()
        conn.close()
        self.reload_tasks()
        self.reload_archive()
        self.update_task_sections()
        if self.tabs.currentIndex() == 1 and self.settings.get("auto_refresh", True):
            self.update_selected_patient()

    def delete_archived_patient(self, room):
        if QMessageBox.question(self, "Onay", f"{room} numaralı arşivlenmiş hasta kalıcı olarak silinsin mi?") != QMessageBox.Yes:
            return
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM archive_patients WHERE room_number=?", (room,))
        conn.commit()
        conn.close()
        self.reload_archive()

    def delete_archived_task(self, task_id):
        if QMessageBox.question(self, "Onay", "Arşivlenmiş görev kalıcı olarak silinsin mi?") != QMessageBox.Yes:
            return
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM archive WHERE id=?", (task_id,))
        conn.commit()
        conn.close()
        self.reload_archive()

    def reload_archive(self):
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM archive_patients ORDER BY room_number")
        pats = cur.fetchall()
        self.archive_patients.setRowCount(0)
        for p in pats:
            row = self.archive_patients.rowCount()
            self.archive_patients.insertRow(row)
            self.archive_patients.setItem(row, 0, QTableWidgetItem(p["room_number"]))
            self.archive_patients.setItem(row, 1, QTableWidgetItem(p["name"]))
            self.archive_patients.setItem(row, 2, QTableWidgetItem(p["surname"]))
            self.archive_patients.setItem(row, 3, QTableWidgetItem(p["tc_no"] or ""))
            btn_restore = QPushButton("Geri Yükle")
            btn_restore.clicked.connect(partial(self.restore_patient, p["room_number"]))
            self.archive_patients.setCellWidget(row, 4, btn_restore)
            btn_delete = QPushButton("Sil")
            btn_delete.clicked.connect(partial(self.delete_archived_patient, p["room_number"]))
            self.archive_patients.setCellWidget(row, 5, btn_delete)
        cur.execute("SELECT a.*, p.name, p.surname FROM archive a LEFT JOIN patients p ON p.room_number=a.room_number ORDER BY a.date DESC")
        at = cur.fetchall()
        self.archive_tasks.setRowCount(0)
        for a in at:
            row = self.archive_tasks.rowCount()
            self.archive_tasks.insertRow(row)
            name = f"{a['room_number']} - {a['name'] or ''} {a['surname'] or ''}"
            self.archive_tasks.setItem(row, 0, QTableWidgetItem(name))
            self.archive_tasks.setItem(row, 1, QTableWidgetItem(a["task"]))
            self.archive_tasks.setItem(row, 2, QTableWidgetItem(a["time"]))
            self.archive_tasks.setItem(row, 3, QTableWidgetItem(a["date"]))
            self.archive_tasks.setItem(row, 4, QTableWidgetItem(a["time_type"]))
            btn_restore = QPushButton("Geri Yükle")
            btn_restore.clicked.connect(partial(self.restore_task, a["id"]))
            self.archive_tasks.setCellWidget(row, 5, btn_restore)
            btn_delete = QPushButton("Sil")
            btn_delete.clicked.connect(partial(self.delete_archived_task, a["id"]))
            self.archive_tasks.setCellWidget(row, 6, btn_delete)
        conn.close()

    def restore_patient(self, room):
        if QMessageBox.question(self, "Onay", f"{room} numaralı hasta geri yüklensin mi?") != QMessageBox.Yes:
            return
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM archive_patients WHERE room_number=?", (room,))
        p = cur.fetchone()
        if p:
            cur.execute(
                "INSERT OR REPLACE INTO patients (room_number,name,surname,notes,photo,tc_no,birth_date,phone) VALUES (?,?,?,?,?,?,?,?)",
                (p["room_number"], p["name"], p["surname"], p["notes"], p["photo"], p["tc_no"], p["birth_date"], p["phone"])
            )
            cur.execute("DELETE FROM archive_patients WHERE room_number=?", (room,))
            conn.commit()
        conn.close()
        self.reload_patients()
        self.reload_archive()

    def restore_task(self, aid):
        if QMessageBox.question(self, "Onay", "Arşivlenmiş görev geri yüklensin mi?") != QMessageBox.Yes:
            return
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM archive WHERE id=?", (aid,))
        a = cur.fetchone()
        if a:
            cur.execute(
                "INSERT INTO tasks (room_number,task,time,date,end_date,time_type,done,cancelled,notified,completed_time) VALUES (?,?,?,?,?,?,0,0,0,NULL)",
                (a["room_number"], a["task"], a["time"], a["date"], a["end_date"], a["time_type"])
            )
            cur.execute("DELETE FROM archive WHERE id=?", (aid,))
            conn.commit()
        conn.close()
        self.reload_tasks()
        self.reload_archive()

    def update_selected_patient(self):
        room = self.patient_selector.currentData()
        self.photo.clear()
        self.photo.setText("Fotoğraf yok")
        self.patient_details.setText("")
        self.patient_task_table.setRowCount(0)
        if not room:
            return
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM patients WHERE room_number=?", (room,))
        p = cur.fetchone()
        if p:
            if p["photo"]:
                pix = QPixmap()
                pix.loadFromData(p["photo"])
                self.photo.setPixmap(pix.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            birth_date = p["birth_date"] or "-"
            try:
                birth_date = datetime.strptime(p["birth_date"], "%Y-%m-%d").strftime("%d/%m/%Y") if p["birth_date"] else "-"
            except:
                pass
            details = f"""
                <div style='line-height: 1.8;'>
                    <h2 style='color: #F1C40F; text-align: center;'>Hasta Bilgileri</h2>
                    <p>
                        <span style='color: #C0392B; font-weight: bold;'>Oda:</span> {p['room_number']}<br>
                        <span style='color: #C0392B; font-weight: bold;'>Ad:</span> {p['name']}<br>
                        <span style='color: #C0392B; font-weight: bold;'>Soyad:</span> {p['surname']}<br>
                        <span style='color: #C0392B; font-weight: bold;'>T.C. No:</span> {p['tc_no'] or '-'}<br>
                        <span style='color: #C0392B; font-weight: bold;'>Doğum Tarihi:</span> {birth_date}<br>
                        <span style='color: #C0392B; font-weight: bold;'>Telefon:</span> {p['phone'] or '-'}<br>
                        <span style='color: #C0392B; font-weight: bold;'>Notlar:</span> {p['notes'] or '-'}
                    </p>
                </div>
            """
            self.patient_details.setHtml(details)
        cur.execute("SELECT * FROM tasks WHERE room_number=? ORDER BY date, time", (room,))
        tasks = cur.fetchall()
        for t in tasks:
            row = self.patient_task_table.rowCount()
            self.patient_task_table.insertRow(row)
            self.patient_task_table.setItem(row, 0, QTableWidgetItem(t["task"]))
            self.patient_task_table.setItem(row, 1, QTableWidgetItem(t["time"] or ""))
            self.patient_task_table.setItem(row, 2, QTableWidgetItem("Tamamlandı" if t["done"] else ("İptal" if t["cancelled"] else "Aktif")))
            self.patient_task_table.setItem(row, 3, QTableWidgetItem(t["repeat_type"] or ""))
            self.patient_task_table.setItem(row, 4, QTableWidgetItem(t["time_type"] or ""))
            e = QPushButton("Düzenle")
            e.clicked.connect(partial(self.edit_task, t["id"]))
            self.patient_task_table.setCellWidget(row, 5, e)
            a = QPushButton("Arşivle")
            a.clicked.connect(partial(self.archive_task, t["id"]))
            self.patient_task_table.setCellWidget(row, 6, a)
            d = QPushButton("Sil")
            d.clicked.connect(partial(self.delete_task, t["id"]))
            self.patient_task_table.setCellWidget(row, 7, d)
        conn.close()

    def add_task_for_selected_patient(self):
        room = self.patient_selector.currentData()
        if not room:
            QMessageBox.warning(self, "Hata", "Lütfen bir hasta seçin.")
            return
        dlg = TaskEditDialog(self, default_room=room)
        if dlg.exec_() == QDialog.Accepted:
            self.reload_tasks()
            self.update_task_sections()
            self.update_selected_patient()

    def is_daytime_task(self, t):
        day_start = self.parse_time(self.settings.get("day_start", "08:00"))
        day_end = self.parse_time(self.settings.get("day_end", "20:00"))
        if t["time_type"] == "Gün İçinde":
            return True
        if t["time_type"] == "Akşam":
            return False
        if t["time"]:
            try:
                hh, mm = map(int, t["time"].split(":"))
                t_time = time(hh, mm)
                return day_start <= t_time < day_end
            except:
                pass
        return False

    def update_task_sections(self):
        # Clear both containers
        while self.day_v.count():
            it = self.day_v.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        while self.night_v.count():
            it = self.night_v.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

        now = datetime.now()
        today = date.today()
        tomorrow = today + timedelta(days=1)
        due_day = []
        completed_day = []
        upcoming_day = []
        cancelled_day = []
        due_night = []
        completed_night = []
        upcoming_night = []
        cancelled_night = []
        day_start = self.parse_time(self.settings.get("day_start", "08:00"))
        day_end = self.parse_time(self.settings.get("day_end", "20:00"))
        timeout_hours = self.settings.get("completed_task_timeout", 4)
        overdue_threshold = timedelta(hours=24)

        # Bugün tamamlanan görevleri yükle
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT task_id FROM task_completions WHERE completion_date=?", (today.isoformat(),))
        completed_tasks = {row["task_id"] for row in cur.fetchall()}
        conn.close()

        for t in self.tasks_cache:
            try:
                t_date = datetime.strptime(t["date"], "%Y-%m-%d").date() if t["date"] else today
                t_end_date = datetime.strptime(t["end_date"], "%Y-%m-%d").date() if t["end_date"] else None
                if t_end_date and t_date > t_end_date:
                    continue
            except:
                t_date = today
            try:
                if t["time"] and t["time_type"] == "Saat Belirt":
                    hh, mm = map(int, t["time"].split(":"))
                    t_time = time(hh, mm)
                    t_dt = datetime.combine(t_date, t_time)
                else:
                    t_time = time(12, 0)
                    t_dt = datetime.combine(t_date, t_time)
            except:
                t_time = time(12, 0)
                t_dt = datetime.combine(t_date, t_time)

            # Skip if more than 24 hours overdue
            if t_dt < now - overdue_threshold:
                continue

            is_daytime = self.is_daytime_task(t)
            is_due = (t_dt <= now and (is_daytime or t["time_type"] == "Akşam") and not t["cancelled"]) or (t["notified"] == 1 and not t["cancelled"])

            is_today = t_date == today
            is_next_24h = t_dt <= now + timedelta(hours=24)

            include = False
            if t["repeat_type"] == "Her Gün":
                include = True
            elif t["repeat_type"] == "Tek Günler" and t_date.day % 2 == 1:
                include = True
            elif t["repeat_type"] == "Çift Günler" and t_date.day % 2 == 0:
                include = True
            elif t["repeat_type"] == "Haftanın Günleri" and t["repeat_days"]:
                days = [int(x) for x in t["repeat_days"].split(",") if x.strip().isdigit()]
                if t_date.weekday() in days:
                    include = True
            elif t["repeat_type"] == "Kaç Günde Bir" and t["repeat_interval"]:
                start_date = datetime.strptime(t["date"], "%Y-%m-%d").date() if t["date"] else today
                delta = (today - start_date).days
                if delta >= 0 and delta % t["repeat_interval"] == 0:
                    include = True
            elif t_date == today:
                include = True

            if not include:
                continue

            if t["id"] in completed_tasks:
                try:
                    completed_dt = now  # task_completions tablosunda tarih var, zamanı şimdilik now kullanıyoruz
                    if (now - completed_dt).total_seconds() / 3600 > timeout_hours:
                        continue
                except:
                    pass

            if t["cancelled"] and is_today:
                if is_daytime:
                    cancelled_day.append((t, t_dt))
                else:
                    cancelled_night.append((t, t_dt))
            elif t["id"] in completed_tasks and is_today:
                if is_daytime:
                    completed_day.append((t, t_dt))
                else:
                    completed_night.append((t, t_dt))
            elif is_due and t["id"] not in completed_tasks:
                if is_daytime:
                    due_day.append((t, t_dt))
                else:
                    due_night.append((t, t_dt))
            elif is_next_24h and t["id"] not in completed_tasks:
                if is_daytime:
                    upcoming_day.append((t, t_dt))
                else:
                    upcoming_night.append((t, t_dt))

        # Update stats (overall)
        total_day = len(completed_day) + len(due_day) + len(cancelled_day)
        total_night = len(completed_night) + len(due_night) + len(cancelled_night)
        self.total_btn.setText(f"Toplam: {total_day + total_night}")
        self.done_btn.setText(f"Tamamlanmış: {len(completed_day) + len(completed_night)}")
        self.wait_btn.setText(f"Vakti Gelen: {len(due_day) + len(due_night)}")
        self.upcoming_btn.setText(f"Gelecek: ({len(upcoming_day) + len(upcoming_night)})")
        self.cancel_btn.setText(f"İptal: {len(cancelled_day) + len(cancelled_night)}")

        def make_section(title, items, is_due_section=False, container=None):
            if not items:
                return
            gb = QGroupBox(f"{title} ({len(items)})")
            vb = QVBoxLayout(gb)
            for t, t_dt in items:
                roww = QWidget()
                hl = QHBoxLayout(roww)
                status = "(Yapıldı)" if t["id"] in completed_tasks else ("(İptal/Stop)" if t["cancelled"] else "(Yapılmadı/Bekliyor)")
                patient_name = f"{t['room_number']} - {t['name'] or ''} {t['surname'] or ''}"
                lbl = QLabel(f"{patient_name} - {t['task']} ({t['time'] or t['time_type'] or ''}) {status}")
                hl.addWidget(lbl)
                hl.addStretch()
                done_btn = QPushButton("✅ Yapıldı")
                notdone_btn = QPushButton("❌ Yapılmadı")
                cancel_btn = QPushButton("🚫 İptal")
                done_btn.setFixedWidth(100)
                notdone_btn.setFixedWidth(100)
                cancel_btn.setFixedWidth(100)
                hl.addWidget(done_btn)
                hl.addWidget(notdone_btn)
                hl.addWidget(cancel_btn)

                roww.setProperty("task_id", t["id"])
                roww.setProperty("is_due", is_due_section)
                roww.setProperty("done", t["id"] in completed_tasks)
                roww.setProperty("cancelled", bool(t["cancelled"]))
                roww.setProperty("is_due_section", is_due_section)

                if t["cancelled"]:
                    color = "#555555"
                elif t["id"] in completed_tasks:
                    color = "#2ecc71"
                else:
                    color = "#7f8c8d" if not is_due_section else "#e74c3c"
                roww.setStyleSheet(f"background:{color}; border-radius:8px; padding:6px; color:white;")
                vb.addWidget(roww)

                done_btn.clicked.connect(partial(self.mark_done, t["id"]))
                notdone_btn.clicked.connect(partial(self.mark_notdone, t["id"]))
                cancel_btn.clicked.connect(partial(self.mark_cancelled, t["id"]))
            container.addWidget(gb)

        # Daytime sections
        make_section("Vakti Gelenler", due_day, True, self.day_v)
        make_section("Tamamlanmış Görevler", completed_day, False, self.day_v)
        make_section("Bir Sonraki Görevler", upcoming_day, False, self.day_v)
        make_section("İptal Edilen Görevler", cancelled_day, False, self.day_v)

        # Night sections
        make_section("Vakti Gelenler", due_night, True, self.night_v)
        make_section("Tamamlanmış Görevler", completed_night, False, self.night_v)
        make_section("Bir Sonraki Görevler", upcoming_night, False, self.night_v)
        make_section("İptal Edilen Görevler", cancelled_night, False, self.night_v)

    def mark_done(self, task_id):
        if QMessageBox.question(self, "Onay", "Görevi tamamlandı olarak işaretlemek istiyor musunuz?") != QMessageBox.Yes:
            return
        conn = get_conn()
        cur = conn.cursor()
        today = date.today().isoformat()
        # Görevi tamamlandı olarak işaretle ve o günü kaydet
        cur.execute("INSERT INTO task_completions (task_id, completion_date) VALUES (?, ?)", (task_id, today))
        # Tekrar eden görevler için done bayrağını sıfırla
        cur.execute("UPDATE tasks SET done=0, completed_time=NULL WHERE id=?", (task_id,))
        conn.commit()
        conn.close()
        self.reload_tasks()
        self.update_task_sections()
        if self.tabs.currentIndex() == 1 and self.settings.get("auto_refresh", True):
            self.update_selected_patient()

    def mark_notdone(self, task_id):
        if QMessageBox.question(self, "Onay", "Görevi yapılmadı olarak işaretlemek istiyor musunuz?") != QMessageBox.Yes:
            return
        conn = get_conn()
        cur = conn.cursor()
        today = date.today().isoformat()
        cur.execute("DELETE FROM task_completions WHERE task_id=? AND completion_date=?", (task_id, today))
        cur.execute("UPDATE tasks SET done=0, cancelled=0, completed_time=NULL WHERE id=?", (task_id,))
        conn.commit()
        conn.close()
        self.reload_tasks()
        self.update_task_sections()
        if self.tabs.currentIndex() == 1 and self.settings.get("auto_refresh", True):
            self.update_selected_patient()

    def mark_cancelled(self, task_id):
        if QMessageBox.question(self, "Onay", "Görevi iptal etmek istiyor musunuz?") != QMessageBox.Yes:
            return
        conn = get_conn()
        cur = conn.cursor()
        today = date.today().isoformat()
        cur.execute("DELETE FROM task_completions WHERE task_id=? AND completion_date=?", (task_id, today))
        cur.execute("UPDATE tasks SET cancelled=1, done=0, completed_time=NULL WHERE id=?", (task_id,))
        conn.commit()
        conn.close()
        self.reload_tasks()
        self.update_task_sections()
        if self.tabs.currentIndex() == 1 and self.settings.get("auto_refresh", True):
            self.update_selected_patient()

    def update_flashing(self):
        self.flash_state = not self.flash_state
        # Update flashing for both subtabs
        for container, subtab in [(self.day_v, self.day_scroll), (self.night_v, self.night_scroll)]:
            for i in range(container.count()):
                item = container.itemAt(i)
                if not item:
                    continue
                w = item.widget()
                if not w:
                    continue
                # "Vakti Gelenler" başlığına sahip QGroupBox için her zaman yanıp sönme
                if isinstance(w, QGroupBox) and w.title().startswith("Vakti Gelenler"):
                    color = "#F1C40F" if self.flash_state else "#E74C3C"
                    w.setStyleSheet(f"""
                        QGroupBox {{
                            background: #333333;
                            color: white;
                            border: 4px solid {color};
                            border-radius: 8px;
                            padding: 10px;
                            font-family: Helvetica;
                            font-size: 16px;
                            font-weight: bold;
                        }}
                        QGroupBox::title {{
                            color: white;
                            subcontrol-origin: margin;
                            subcontrol-position: top left;
                            padding: 0 3px;
                        }}
                    """)
                    continue  # Vakti Gelenler için işlemi bitir, altındaki roww'ları kontrol etmeye gerek yok

                # Diğer görev satırları için mevcut mantık
                for j in range(w.layout().count()):
                    roww = w.layout().itemAt(j).widget()
                    if not roww:
                        continue
                    is_due = roww.property("is_due")
                    done = roww.property("done")
                    cancelled = roww.property("cancelled")
                    is_due_section = roww.property("is_due_section")
                    if is_due_section and is_due and not done and not cancelled:
                        color = "#F1C40F" if self.flash_state else "#E74C3C"
                        roww.setStyleSheet(f"background:{color}; border-radius:8px; padding:6px; color:white;")
                    else:
                        if done:
                            roww.setStyleSheet("background:#2ecc71; border-radius:8px; padding:6px; color:white;")
                        elif cancelled:
                            roww.setStyleSheet("background:#555555; border-radius:8px; padding:6px; color:white;")
                        else:
                            roww.setStyleSheet("background:#7f8c8d; border-radius:8px; padding:6px; color:white;")

    def check_notifications(self):
        if not self.settings.get("notifications_enabled", True):
            return
        now = datetime.now()
        day_start = self.parse_time(self.settings.get("day_start", "08:00"))
        night_start = self.parse_time(self.settings.get("night_start", "20:00"))
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT t.*, p.name, p.surname, p.photo FROM tasks t LEFT JOIN patients p ON p.room_number=t.room_number WHERE done=0 AND cancelled=0 AND (notified=0 OR notified IS NULL)")
        rows = cur.fetchall()
        for r in rows:
            try:
                tdt = None
                if r["time"] and r["time_type"] == "Saat Belirt":
                    hh, mm = map(int, r["time"].split(":"))
                    tdt = datetime.combine(datetime.strptime(r["date"], "%Y-%m-%d").date() if r["date"] else date.today(), time(hh, mm))
                elif r["time_type"] == "Gün İçinde":
                    tdt = datetime.combine(datetime.strptime(r["date"], "%Y-%m-%d").date() if r["date"] else date.today(), day_start)
                elif r["time_type"] == "Akşam":
                    tdt = datetime.combine(datetime.strptime(r["date"], "%Y-%m-%d").date() if r["date"] else date.today(), night_start)
                
                if tdt:
                    diff = (tdt - now).total_seconds()
                    if -300 <= diff <= 300:  # Within 5 minutes before or after the task time
                        patient_name = f"{r['room_number']} - {r['name'] or ''} {r['surname'] or ''}"
                        time_info = r["time"] if r["time_type"] == "Saat Belirt" else r["time_type"]
                        message = f"Görev Hatırlatması\nHasta: {patient_name}\nGörev: {r['task']}\nZaman: {time_info}"
                        dlg = NotificationDialog(self, message, r["id"], r["photo"])
                        dlg.exec_()
                        cur.execute("UPDATE tasks SET notified=1 WHERE id=?", (r["id"],))
                        conn.commit()
                        break  # Show one notification at a time to avoid overwhelming the user
            except Exception as e:
                print(f"Notification error: {e}")
        conn.close()

    def reload_calendar_tasks(self):
        sel = self.calendar.selectedDate().toPyDate()
        weekday = sel.weekday()
        conn = get_conn()
        cur = conn.cursor()
        # Görevleri yükle
        cur.execute("SELECT t.*, p.name, p.surname FROM tasks t LEFT JOIN patients p ON p.room_number=t.room_number")
        rows = cur.fetchall()
        # Seçilen gün için tamamlanmış görevleri yükle
        cur.execute("SELECT task_id FROM task_completions WHERE completion_date=?", (sel.isoformat(),))
        completed_tasks = {row["task_id"] for row in cur.fetchall()}
        conn.close()
        
        display = []
        timeout_hours = self.settings.get("completed_task_timeout", 4)
        now = datetime.now()
        today = date.today()
        overdue_threshold = timedelta(hours=24)
        
        for r in rows:
            include = False
            try:
                t_date = datetime.strptime(r["date"], "%Y-%m-%d").date() if r["date"] else today
                t_end_date = datetime.strptime(r["end_date"], "%Y-%m-%d").date() if r["end_date"] else None
                if t_end_date and sel > t_end_date:
                    continue
                rt = r["repeat_type"] or ""
                if r["date"] and t_date == sel:
                    include = True
                elif rt == "Her Gün":
                    include = True
                elif rt == "Tek Günler" and sel.day % 2 == 1:
                    include = True
                elif rt == "Çift Günler" and sel.day % 2 == 0:
                    include = True
                elif rt == "Haftanın Günleri" and r["repeat_days"]:
                    days = [int(x) for x in r["repeat_days"].split(",") if x.strip().isdigit()]
                    if weekday in days:
                        include = True
                elif rt == "Kaç Günde Bir" and r["repeat_interval"]:
                    start_date = datetime.strptime(r["date"], "%Y-%m-%d").date() if r["date"] else today
                    delta = (sel - start_date).days
                    if delta >= 0 and delta % r["repeat_interval"] == 0:
                        include = True
            except Exception:
                pass
            if include:
                # Skip overdue
                try:
                    if r["time"] and r["time_type"] == "Saat Belirt":
                        hh, mm = map(int, r["time"].split(":"))
                        tdt = datetime.combine(sel, time(hh, mm))
                    else:
                        tdt = datetime.combine(sel, time(12, 0))
                    if tdt < now - overdue_threshold:
                        continue
                except:
                    pass
                display.append((r, r["id"] in completed_tasks))
        
        self.calendar_table.setRowCount(0)
        for r, is_completed in display:
            row = self.calendar_table.rowCount()
            self.calendar_table.insertRow(row)
            name = f"{r['room_number']} - {r['name'] or ''} {r['surname'] or ''}"
            self.calendar_table.setItem(row, 0, QTableWidgetItem(name))
            self.calendar_table.setItem(row, 1, QTableWidgetItem(r["task"]))
            self.calendar_table.setItem(row, 2, QTableWidgetItem(r["time"] or ""))
            status = "Tamamlandı" if is_completed else ("İptal" if r["cancelled"] else ("Bekleniyor" if (r["time"] and datetime.combine(sel, time(int(r["time"].split(':')[0]), int(r["time"].split(':')[1]))) <= now) else "Gelecek"))
            self.calendar_table.setItem(row, 3, QTableWidgetItem(status))
            self.calendar_table.setItem(row, 4, QTableWidgetItem(r["repeat_type"] or ""))
            self.calendar_table.setItem(row, 5, QTableWidgetItem(r["time_type"] or ""))
            if r["cancelled"]:
                color = QtGui.QColor("#555555")
            elif is_completed:
                color = QtGui.QColor("#2ecc71")
            else:
                if r["time"]:
                    try:
                        hh, mm = map(int, r["time"].split(":"))
                        tdt = datetime.combine(sel, time(hh, mm))
                        if tdt <= now:
                            color = QtGui.QColor("#e74c3c")
                        else:
                            color = QtGui.QColor("#7f8c8d")
                    except:
                        color = QtGui.QColor("#7f8c8d")
                else:
                    color = QtGui.QColor("#7f8c8d")
            for c in range(self.calendar_table.columnCount()):
                it = self.calendar_table.item(row, c)
                if it:
                    it.setBackground(color)
                    it.setForeground(QtGui.QBrush(Qt.white))

    def show_task_list(self, kind):
        conn = get_conn()
        cur = conn.cursor()
        timeout_hours = self.settings.get("completed_task_timeout", 4)
        now = datetime.now()
        today = date.today()
        overdue_threshold = timedelta(hours=24)
        if kind == "all":
            cur.execute("SELECT t.*, p.name, p.surname FROM tasks t LEFT JOIN patients p ON p.room_number=t.room_number WHERE t.date=?", (today.isoformat(),))
        elif kind == "done":
            cur.execute("SELECT t.*, p.name, p.surname FROM tasks t LEFT JOIN patients p ON p.room_number=t.room_number WHERE done=1 AND t.date=?", (today.isoformat(),))
        elif kind == "waiting":
            cur.execute("SELECT t.*, p.name, p.surname FROM tasks t LEFT JOIN patients p ON p.room_number=t.room_number WHERE done=0 AND cancelled=0 AND t.date=?", (today.isoformat(),))
        elif kind == "upcoming":
            cur.execute("SELECT t.*, p.name, p.surname FROM tasks t LEFT JOIN patients p ON p.room_number=t.room_number WHERE t.date > ? AND t.date <= ?", (today.isoformat(), (today + timedelta(days=1)).isoformat()))
        elif kind == "cancelled":
            cur.execute("SELECT t.*, p.name, p.surname FROM tasks t LEFT JOIN patients p ON p.room_number=t.room_number WHERE cancelled=1 AND t.date=?", (today.isoformat(),))
        rows = cur.fetchall()
        conn.close()
        tasks = []
        for r in rows:
            # Skip overdue
            try:
                if r["time"] and r["time_type"] == "Saat Belirt":
                    hh, mm = map(int, r["time"].split(":"))
                    tdt = datetime.combine(today, time(hh, mm))
                else:
                    tdt = datetime.combine(today, time(12, 0))
                if tdt < now - overdue_threshold:
                    continue
            except:
                pass
            if r["done"] and r["completed_time"]:
                try:
                    completed_dt = datetime.strptime(r["completed_time"], "%Y-%m-%d %H:%M:%S")
                    if (now - completed_dt).total_seconds() / 3600 > timeout_hours:
                        continue
                except:
                    pass
            tasks.append({
                "patient": f"{r['room_number']} - {r['name'] or ''} {r['surname'] or ''}",
                "task": r['task'],
                "time": r['time'],
                "time_type": r['time_type']
            })
        dlg = TaskListDialog(self, tasks, title="Görevler")
        dlg.exec_()

    def update_clock(self):
        now = datetime.now()
        month_name = TURKISH_MONTHS[now.month]
        clock_format = self.settings.get("clock_format", "24 Saat")
        if clock_format == "12 Saat":
            time_str = now.strftime("%I:%M:%S %p")
        else:
            time_str = now.strftime("%H:%M:%S")
        self.center_clock.setText(f"<div style='font-size: 48px;'>{time_str}</div><div style='font-size: 18px;'>{now.strftime(f'%d {month_name} %Y')}</div>")

    def apply_theme(self, name):
        t = THEMES.get(name, THEMES["Galatasaray"])
        font_size = self.settings.get("font_size", 14)
        grad = f"background: qlineargradient(x1:0 y1:0 x2:1 y2:1, stop:0 {t['bg_start']}, stop:1 {t['bg_end']});"
        text = t['text']
        self.setStyleSheet(f"""
            QMainWindow {{ {grad} color:{text}; font-size: {font_size}px; }}
            QPushButton {{ background:{t['button']}; color: white; border-radius:8px; padding:6px; font-size: {font_size}px; }}
            QPushButton:hover {{ background:{t['button_hover']}; }}
            QLabel {{ color: {text}; font-size: {font_size}px; }}
            QGroupBox {{ color: {text}; font-size: {font_size}px; }}
            QTextEdit {{ color: {text}; background: transparent; font-size: {font_size}px; }}
            QComboBox {{ color: {text}; background: {t['table_bg']}; font-size: {font_size}px; }}
            QTableWidget {{ color: {text}; background: {t['table_bg']}; font-size: {font_size}px; }}
            QLineEdit {{ color: {text}; background: {t['table_bg']}; border: 1px solid {t['button']}; font-size: {font_size}px; }}
            QDateEdit {{ color: #000000; background: white; font-size: {font_size}px; }}
            QTimeEdit {{ color: #000000; background: white; font-size: {font_size}px; }}
            QSpinBox {{ color: #000000; background: white; font-size: {font_size}px; }}
        """)
        # Özel tablo arka planları: Çok açık gri (#F5F5F5)
        light_gray = "#F5F5F5"
        self.patient_task_table.setStyleSheet(f"""
            QTableWidget {{ background: {light_gray}; color: {text}; font-size: {font_size}px; }}
            QTableWidget::item {{ background: {light_gray}; color: {text}; }}
        """)
        self.tasks_table.setStyleSheet(f"""
            QTableWidget {{ background: {light_gray}; color: {text}; font-size: {font_size}px; }}
            QTableWidget::item {{ background: {light_gray}; color: {text}; }}
        """)
        self.archive_patients.setStyleSheet(f"""
            QTableWidget {{ background: {light_gray}; color: {text}; font-size: {font_size}px; }}
            QTableWidget::item {{ background: {light_gray}; color: {text}; }}
        """)
        self.archive_tasks.setStyleSheet(f"""
            QTableWidget {{ background: {light_gray}; color: {text}; font-size: {font_size}px; }}
            QTableWidget::item {{ background: {light_gray}; color: {text}; }}
        """)
        self.update_theme_preview()

    def apply_font_size(self, sz):
        f = QFont("Helvetica", sz)
        self.setFont(f)
        # Tüm alt widget'lara yazı tipini uygula
        def set_font_recursive(widget, font):
            widget.setFont(font)
            for child in widget.findChildren(QtWidgets.QWidget):
                set_font_recursive(child, font)
        set_font_recursive(self, f)
        # Stil sayfalarını güncelle
        self.apply_theme(self.settings.get("theme", "Galatasaray"))

    def on_theme_changed(self, i):
        name = self.theme_combo.currentText()
        self.settings["theme"] = name
        save_settings(self.settings)
        self.apply_theme(name)

    def on_font_changed(self, val):
        self.settings["font_size"] = val
        save_settings(self.settings)
        self.apply_font_size(val)
        self.apply_theme(self.settings.get("theme", "Galatasaray"))  # Tema ve yazı boyutunu yeniden uygula
        self.refresh_all()  # Tüm bölümleri yenile

    def on_notify_changed(self, state):
        self.settings["notifications_enabled"] = bool(state)
        save_settings(self.settings)

    def on_timeout_changed(self, i):
        self.settings["completed_task_timeout"] = int(self.timeout_combo.currentText())
        save_settings(self.settings)
        self.refresh_all()

    def on_clock_format_changed(self, i):
        self.settings["clock_format"] = self.clock_format.currentText()
        save_settings(self.settings)
        self.update_clock()

    def on_auto_refresh_changed(self, state):
        self.settings["auto_refresh"] = bool(state)
        save_settings(self.settings)

    def on_notification_duration_changed(self, val):
        self.settings["notification_duration"] = val
        save_settings(self.settings)

    def on_day_start_changed(self, time_val):
        self.settings["day_start"] = time_val.toString("HH:mm")
        save_settings(self.settings)
        self.refresh_all()

    def on_day_end_changed(self, time_val):
        self.settings["day_end"] = time_val.toString("HH:mm")
        save_settings(self.settings)
        self.refresh_all()

    def on_night_start_changed(self, time_val):
        self.settings["night_start"] = time_val.toString("HH:mm")
        save_settings(self.settings)
        self.refresh_all()

    def on_night_end_changed(self, time_val):
        self.settings["night_end"] = time_val.toString("HH:mm")
        save_settings(self.settings)
        self.refresh_all()

    def update_theme_preview(self):
        t = THEMES.get(self.theme_combo.currentText(), THEMES["Galatasaray"])
        self.theme_preview.setStyleSheet(f"background: qlineargradient(x1:0 y1:0 x2:1 y2:1, stop:0 {t['bg_start']}, stop:1 {t['bg_end']}); color: {t['text']}; border-radius:8px; padding:8px;")

def main():
    app = QApplication(sys.argv)
    splash = SplashScreen()
    splash.show()
    main_win = PatientTaskApp()
    def open_main():
        main_win.show()
    splash.finished.connect(open_main)
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
