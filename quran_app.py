import sys
import os
import json
import subprocess
import threading
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QFileDialog, QProgressBar, QSlider, 
                             QGroupBox, QFormLayout, QMessageBox, QScrollArea)
from PyQt6.QtCore import Qt, pyqtSignal, QObject

class VideoWorker(QObject):
    progress = pyqtSignal(int)
    total_progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    preview_ready = pyqtSignal(str)

    def __init__(self, config, chroma_files, template_video, surah_dir, qari_dir, output_dir):
        super().__init__()
        self.config = config
        self.chroma_files = chroma_files
        self.template_video = template_video
        self.surah_dir = surah_dir
        self.qari_dir = qari_dir
        self.output_dir = output_dir
        self.is_running = True

    def run_ffmpeg(self, inputs, filters, final_filter, output_path):
        command = f"ffmpeg {' '.join(inputs)} -filter_complex \"{';'.join(filters)}\" {final_filter} -y \"{output_path}\""
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        
        # Simple progress estimation (not perfect for FFmpeg but gives feedback)
        for line in process.stdout:
            if not self.is_running:
                process.terminate()
                return False
            # You could parse duration here for better progress, but keeping it simple for stability
            pass
        
        process.wait()
        return process.returncode == 0

    def generate_preview(self):
        if not self.chroma_files:
            self.error.emit("لا توجد ملفات كروما!")
            return

        chroma_file = self.chroma_files[0]
        chroma_path = os.path.join(os.path.dirname(self.chroma_files[0]), chroma_file)
        output_path = os.path.join(self.output_dir, "preview.png")
        
        inputs, filters = self.build_ffmpeg_params(chroma_path)
        command = f"ffmpeg {' '.join(inputs)} -filter_complex \"{';'.join(filters)}\" -frames:v 1 -y \"{output_path}\""
        
        try:
            subprocess.run(command, shell=True, check=True)
            self.preview_ready.emit(output_path)
        except Exception as e:
            self.error.emit(f"خطأ في المعاينة: {str(e)}")

    def build_ffmpeg_params(self, chroma_path):
        inputs = [f"-i \"{self.template_video}\"", f"-i \"{chroma_path}\""]
        filters = []
        
        # Chroma Overlay
        c = self.config['chroma']
        filters.append(f"[1:v]scale=iw*{c['scale']}:-1[c_sc];[0:v][c_sc]overlay={c['x']}:{c['y']}:format=auto:shortest=1[v1]")
        
        curr_v = "v1"
        input_idx = 2
        
        # Surah Name
        surah_img = self.find_matching_image(chroma_path, self.surah_dir)
        if surah_img:
            inputs.append(f"-i \"{surah_img}\"")
            s = self.config['surah']
            filters.append(f"[{input_idx}:v]scale=iw*{s['scale']}:-1[s_sc];[{curr_v}][s_sc]overlay={s['x']}:{s['y']}:format=auto[v2]")
            curr_v = "v2"
            input_idx += 1
            
        # Qari Name
        qari_img = self.get_first_image(self.qari_dir)
        if qari_img:
            inputs.append(f"-i \"{qari_img}\"")
            q = self.config['qari']
            filters.append(f"[{input_idx}:v]scale=iw*{q['scale']}:-1[q_sc];[{curr_v}][q_sc]overlay={q['x']}:{q['y']}:format=auto[final]")
            curr_v = "final"
            
        return inputs, filters

    def find_matching_image(self, chroma_path, directory):
        base = os.path.splitext(os.path.basename(chroma_path))[0].split('_')[0]
        for f in os.listdir(directory):
            if f.startswith(base) and f.lower().endswith(('.png', '.jpg', '.jpeg')):
                return os.path.join(directory, f)
        return None

    def get_first_image(self, directory):
        for f in os.listdir(directory):
            if f.lower().endswith(('.png', '.jpg', '.jpeg')):
                return os.path.join(directory, f)
        return None

    def process_all(self):
        total = len(self.chroma_files)
        for i, chroma_path in enumerate(self.chroma_files):
            if not self.is_running: break
            
            output_name = f"final_{os.path.basename(chroma_path)}"
            output_path = os.path.join(self.output_dir, output_name)
            
            inputs, filters = self.build_ffmpeg_params(chroma_path)
            res = self.config['resolution']
            final_filter = f"-map \"[final]\" -map 1:a? -c:v libx264 -preset ultrafast -crf 23 -c:a aac -b:a 192k -vf \"format=yuv420p,scale={res}\""
            # If no qari/surah, adjust final stream name
            if "[final]" not in ";".join(filters):
                if "[v2]" in ";".join(filters): final_filter = final_filter.replace("[final]", "[v2]")
                else: final_filter = final_filter.replace("[final]", "[v1]")

            success = self.run_ffmpeg(inputs, filters, final_filter, output_path)
            if success:
                self.total_progress.emit(int(((i + 1) / total) * 100))
            else:
                self.error.emit(f"فشل معالجة: {os.path.basename(chroma_path)}")
        
        if self.is_running:
            self.finished.emit("تم الانتهاء من جميع الفيديوهات!")

class QuranApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("صانع فيديوهات القرآن الاحترافي - 4K")
        self.setMinimumSize(800, 600)
        self.init_ui()
        self.config = {
            'resolution': '3840x2160',
            'chroma': {'x': '(W-w)/2', 'y': '(H-h)/2', 'scale': 1.0},
            'surah': {'x': 'W-w-50', 'y': '50', 'scale': 0.5},
            'qari': {'x': '50', 'y': 'H-h-50', 'scale': 0.5}
        }

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- File Selection ---
        file_group = QGroupBox("إعداد الملفات")
        file_layout = QFormLayout()
        
        self.btn_template = QPushButton("اختر قالب الفيديو")
        self.btn_template.clicked.connect(self.select_template)
        self.lbl_template = QLabel("لم يتم الاختيار")
        file_layout.addRow(self.btn_template, self.lbl_template)

        self.btn_chromas = QPushButton("اختر مجلد الكرومات")
        self.btn_chromas.clicked.connect(self.select_chromas)
        self.lbl_chromas = QLabel("لم يتم الاختيار")
        file_layout.addRow(self.btn_chromas, self.lbl_chromas)

        self.btn_surah = QPushButton("اختر مجلد أسماء السور")
        self.btn_surah.clicked.connect(lambda: self.select_dir('surah'))
        self.lbl_surah = QLabel("لم يتم الاختيار")
        file_layout.addRow(self.btn_surah, self.lbl_surah)

        self.btn_qari = QPushButton("اختر مجلد أسماء القراء")
        self.btn_qari.clicked.connect(lambda: self.select_dir('qari'))
        self.lbl_qari = QLabel("لم يتم الاختيار")
        file_layout.addRow(self.btn_qari, self.lbl_qari)

        self.btn_output = QPushButton("اختر مجلد المخرجات")
        self.btn_output.clicked.connect(lambda: self.select_dir('output'))
        self.lbl_output = QLabel("لم يتم الاختيار")
        file_layout.addRow(self.btn_output, self.lbl_output)

        file_group.setLayout(file_layout)
        main_layout.addWidget(file_group)

        # --- Layout Controls ---
        control_group = QGroupBox("تخطيط العناصر (المكان والحجم)")
        control_layout = QVBoxLayout()
        
        # We'll use simple text inputs for positions to allow FFmpeg formulas like (W-w)/2
        from PyQt6.QtWidgets import QLineEdit
        
        self.chroma_x = QLineEdit("(W-w)/2")
        self.chroma_y = QLineEdit("(H-h)/2")
        self.chroma_scale = QSlider(Qt.Orientation.Horizontal)
        self.chroma_scale.setRange(1, 200); self.chroma_scale.setValue(100)
        
        layout_form = QFormLayout()
        layout_form.addRow("مكان الكروما X:", self.chroma_x)
        layout_form.addRow("مكان الكروما Y:", self.chroma_y)
        layout_form.addRow("حجم الكروما %:", self.chroma_scale)
        control_group.setLayout(layout_form)
        main_layout.addWidget(control_group)

        # --- Progress ---
        self.progress_bar = QProgressBar()
        self.status_label = QLabel("جاهز للبدء")
        main_layout.addWidget(QLabel("التقدم الإجمالي:"))
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(self.status_label)

        # --- Buttons ---
        btn_layout = QHBoxLayout()
        self.btn_preview = QPushButton("توليد معاينة")
        self.btn_preview.clicked.connect(self.start_preview)
        self.btn_start = QPushButton("بدء الإنتاج الكامل")
        self.btn_start.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; height: 40px;")
        self.btn_start.clicked.connect(self.start_production)
        
        btn_layout.addWidget(self.btn_preview)
        btn_layout.addWidget(self.btn_start)
        main_layout.addLayout(btn_layout)

    def select_template(self):
        file, _ = QFileDialog.getOpenFileName(self, "اختر قالب الفيديو", "", "Video Files (*.mp4 *.mov *.avi)")
        if file: self.lbl_template.setText(os.path.basename(file)); self.template_path = file

    def select_chromas(self):
        directory = QFileDialog.getExistingDirectory(self, "اختر مجلد الكرومات")
        if directory:
            self.chroma_dir = directory
            self.chroma_files = [os.path.join(directory, f) for f in os.listdir(directory) if f.lower().endswith(('.mp4', '.mov'))]
            self.lbl_chromas.setText(f"تم اختيار {len(self.chroma_files)} فيديو")

    def select_dir(self, type):
        directory = QFileDialog.getExistingDirectory(self, f"اختر مجلد {type}")
        if directory:
            setattr(self, f"{type}_dir", directory)
            getattr(self, f"lbl_{type}").setText("تم الاختيار")

    def update_config(self):
        self.config['chroma']['x'] = self.chroma_x.text()
        self.config['chroma']['y'] = self.chroma_y.text()
        self.config['chroma']['scale'] = self.chroma_scale.value() / 100.0

    def start_preview(self):
        if not hasattr(self, 'template_path') or not hasattr(self, 'chroma_files'):
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار القالب ومجلد الكرومات أولاً!")
            return
        self.update_config()
        self.worker = VideoWorker(self.config, self.chroma_files, self.template_path, self.surah_dir, self.qari_dir, self.output_dir)
        self.worker.preview_ready.connect(self.show_preview_msg)
        self.worker.error.connect(lambda e: QMessageBox.critical(self, "خطأ", e))
        threading.Thread(target=self.worker.generate_preview).start()

    def show_preview_msg(self, path):
        QMessageBox.information(self, "تمت المعاينة", f"تم إنشاء صورة المعاينة في مجلد المخرجات:\n{path}")

    def start_production(self):
        if not hasattr(self, 'template_path') or not hasattr(self, 'chroma_files'):
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار كافة المجلدات أولاً!")
            return
        self.update_config()
        self.btn_start.setEnabled(False)
        self.status_label.setText("جاري الإنتاج... يرجى الانتظار")
        
        self.worker = VideoWorker(self.config, self.chroma_files, self.template_path, self.surah_dir, self.qari_dir, self.output_dir)
        self.worker.total_progress.connect(self.progress_bar.setValue)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(lambda e: self.status_label.setText(f"خطأ: {e}"))
        
        self.thread = threading.Thread(target=self.worker.process_all)
        self.thread.start()

    def on_finished(self, msg):
        self.btn_start.setEnabled(True)
        self.status_label.setText(msg)
        QMessageBox.information(self, "تم بنجاح", msg)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = QuranApp()
    window.show()
    sys.exit(app.exec())
