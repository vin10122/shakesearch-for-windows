"""Persistent status window and first-run configuration."""
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QSystemTrayIcon,
    QToolTip, QVBoxLayout, QWidget)
from PySide6.QtGui import QIcon
from app_icon import icon_path
from localization import get_language
from app_version import VERSION
from app_settings import preferences, save_preferences


def label(it, en):
    return en if get_language() == 'en' else it


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(label('Configurazione ShakeSearch', 'ShakeSearch settings'))
        layout = QFormLayout(self)
        info = QLabel(label('Il ritaglio e le domande vengono inviati a Google Lens.\nCompleta eventuali richieste di consenso nella finestra Google.',
                            'Captures and questions are sent to Google Lens.\nComplete any consent requests in the Google window.'))
        info.setWordWrap(True)
        layout.addRow(info)
        values = preferences()
        self.language = QComboBox()
        for text, value in [('Italiano', 'it'), ('English', 'en')]:
            self.language.addItem(text, value)
        self.language.setCurrentIndex(self.language.findData(get_language()))
        layout.addRow('Lingua / Language', self.language)
        self.shake = QCheckBox(label('Attiva scuotendo il mouse', 'Activate by shaking the mouse'))
        self.shake.setChecked(values['shake_enabled'])
        layout.addRow(self.shake)
        self.sensitivity = QComboBox()
        for text, value in [(label('Bassa', 'Low'), 'low'), (label('Normale', 'Normal'), 'normal'), (label('Alta', 'High'), 'high')]:
            self.sensitivity.addItem(text, value)
        self.sensitivity.setCurrentIndex(self.sensitivity.findData(values['sensitivity']))
        layout.addRow(label('Sensibilità', 'Sensitivity'), self.sensitivity)
        self.animation = QComboBox()
        self.animation.addItem(label('Bilanciata (60 fps)', 'Balanced (60 fps)'), 'balanced')
        self.animation.addItem(label('Leggera (solo bordo)', 'Light (border only)'), 'light')
        self.animation.setCurrentIndex(self.animation.findData(values['animation']))
        layout.addRow(label('Animazione', 'Animation'), self.animation)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def save(self):
        try:
            save_preferences(self.language.currentData(), self.shake.isChecked(),
                             self.sensitivity.currentData(), self.animation.currentData())
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, 'ShakeSearch', str(error))
            return
        self.accept()


class ControlPanel(QMainWindow):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.tray = QSystemTrayIcon(QIcon(str(icon_path())), self)
        controller.application.aboutToQuit.connect(self.tray.hide)
        self.setWindowTitle('ShakeSearch ' + VERSION)
        self.resize(430, 260)
        container = QWidget()
        self.setCentralWidget(container)
        layout = QVBoxLayout(container)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.capture = QPushButton()
        self.capture.clicked.connect(self.capture_now)
        layout.addWidget(self.capture)
        self.configure = QPushButton()
        self.configure.clicked.connect(self.settings)
        layout.addWidget(self.configure)
        self.quit_button = QPushButton()
        self.quit_button.clicked.connect(controller.application.quit)
        layout.addWidget(self.quit_button)
        self.refresh()

    def refresh(self):
        title, message = self.shake_status()
        self.status.setText(title + '\n' + message)
        self.tray.setToolTip(title)
        self.capture.setText(label('Seleziona area', 'Select area'))
        self.configure.setText(label('Configurazione', 'Settings'))
        self.quit_button.setText(label('Esci', 'Quit'))

    def shake_status(self):
        if self.controller.options['shake_enabled']:
            return (label('ShakeSearch — Shake attivi', 'ShakeSearch — Shakes enabled'),
                    label('Scuoti il mouse oppure premi Seleziona area. Alt+F7 attiva la Gaming mode.',
                          'Shake the mouse or press Select area. Alt+F7 enables Gaming mode.'))
        return ('ShakeSearch — Gaming mode',
                label('Shake disattivati per evitare interferenze mentre giochi con DPI alti. '
                      'Seleziona area resta disponibile. Alt+F7 riattiva gli shake.',
                      'Shakes disabled to avoid interference while gaming with high DPI. '
                      'Select area remains available. Alt+F7 re-enables shakes.'))

    def notify_shake_state(self):
        title, message = self.shake_status()
        if QSystemTrayIcon.isSystemTrayAvailable():
            if not self.tray.isVisible():
                self.tray.show()
            self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 5000)
        else:
            # A nonmodal fallback for desktops without a notification area.
            QToolTip.showText(self.mapToGlobal(self.rect().center()), title + '\n' + message, self)

    def capture_now(self):
        self.controller.trigger_capture()

    def settings(self):
        was_enabled = self.controller.options['shake_enabled']
        if SettingsDialog(self).exec() == QDialog.DialogCode.Accepted:
            self.controller.reload_preferences()
            self.refresh()
            if self.controller.options['shake_enabled'] != was_enabled:
                self.notify_shake_state()

    def closeEvent(self, event):
        # Closing this window stops the app; it never silently remains running.
        self.controller.application.quit()
        self.tray.hide()
        event.accept()
