# app.py
import sys
import os
import shutil
import logging
import time
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QFileDialog, QVBoxLayout, QWidget,
                             QProgressBar, QMessageBox, QLineEdit, QTableView, QHBoxLayout,
                             QLabel, QComboBox, QMenu, QAction, QDialog, QFormLayout, QHeaderView,
                             QStyle, QToolTip, QStatusBar, QStyledItemDelegate, QMenuBar, QScrollArea)
from PyQt5.QtCore import (QThread, pyqtSignal, Qt, QSortFilterProxyModel, QDate, QEvent,
                          QStandardPaths, QUrl, QTimer)
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QColor, QBrush, QIcon, QFontMetrics, QDesktopServices
import fitz
import re
import pandas as pd
import sqlite3
import config
from secure_dropbox_auth import SecureDropboxAuth
import dropbox
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
from openai import OpenAI
import json
import PyPDF2
from dotenv import load_dotenv
from pathlib import Path
import base64

load_dotenv()  # Tilføj denne linje

# For at debugge, tilføj denne linje midlertidigt efter load_dotenv():
logging.info(f"API Key loaded: {'OPENAI_API_KEY' in os.environ}")


def get_app_data_dir():
    data_dir = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    app_data_dir = os.path.join(data_dir, "Sweetspot Data Håndtering")
    os.makedirs(app_data_dir, exist_ok=True)
    return app_data_dir


def setup_logging():
    log_dir = get_app_data_dir()
    log_file = os.path.join(log_dir, 'sweetspot.log')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

    logging.info("Logging setup completed")


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    # Tjek først i icons mappen
    icon_path = os.path.join(base_path, 'icons', relative_path)
    if os.path.exists(icon_path):
        return icon_path
    
    # Ellers returner den almindelige sti
    return os.path.join(base_path, relative_path)


class DateSortFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, date_column_index, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.date_column_index = date_column_index

    def lessThan(self, left, right):
        if left.column() == self.date_column_index:
            leftData = self.sourceModel().data(left)
            rightData = self.sourceModel().data(right)

            leftDate = QDate.fromString(leftData, "dd.MM.yyyy")
            rightDate = QDate.fromString(rightData, "dd.MM.yyyy")

            if leftDate.isValid() and rightDate.isValid():
                return leftDate < rightDate
            elif leftDate.isValid():
                return True
            elif rightDate.isValid():
                return False
            else:
                return super().lessThan(left, right)
        else:
            return super().lessThan(left, right)


class DropboxSync(QThread):
    status = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, local_file_path, dbx_client):
        super().__init__()
        self.local_file_path = local_file_path
        self.dbx_client = dbx_client

    def run(self):
        try:
            file_name = os.path.basename(self.local_file_path)
            if not os.path.exists(self.local_file_path):
                raise FileNotFoundError(f"Filen {self.local_file_path} blev ikke fundet.")
            with open(self.local_file_path, 'rb') as f:
                self.dbx_client.files_upload(f.read(), f'/{file_name}', mode=dropbox.files.WriteMode.overwrite)
            self.status.emit(f"Fil uploadet til Dropbox: {file_name}")
        except dropbox.exceptions.AuthError as e:
            logging.error(f"Dropbox autentificeringsfejl: {e}")
            self.status.emit("Dropbox autentificeringsfejl. Kontroller din Dropbox adgang.")
            QMessageBox.critical(None, "Dropbox Fejl",
                                 "Autentificeringsfejl med Dropbox. Kontroller din adgangstoken.")
        except dropbox.exceptions.ApiError as e:
            logging.error(f"Dropbox API fejl: {e}")
            self.status.emit("Dropbox API fejl. Prøv igen senere.")
            QMessageBox.critical(None, "Dropbox Fejl",
                                 "Der opstod en fejl med Dropbox API'en. Prøv igen senere.")
        except dropbox.exceptions.HttpError as e:
            logging.error(f"Dropbox netværksfejl: {e}")
            self.status.emit("Netværksfejl. Kontroller din internetforbindelse.")
            QMessageBox.critical(None, "Netværksfejl",
                                 "Der opstod en netværksfejl. Kontroller din internetforbindelse.")
        except Exception as e:
            logging.error(f"Fejl ved upload til Dropbox: {e}")
            self.status.emit(f"Fejl ved upload til Dropbox: {str(e)}")
            QMessageBox.critical(None, "Fejl ved upload til Dropbox",
                                 f"Der opstod en fejl ved upload til Dropbox:\n{e}")
        finally:
            self.finished.emit()


class PDFProcessor(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)  # Ny signal for fejlhåndtering
    info = pyqtSignal(str, str)  # Ny signal for info beskeder (titel, besked)

    def __init__(self, pdf_path, db_path):
        super().__init__()
        self.pdf_path = pdf_path
        self.pdf_name = os.path.basename(pdf_path)
        self.db_path = db_path
        self.total_products = 0
        self._is_running = True

    def stop(self):
        self._is_running = False

    def safe_emit(self, signal, *args):
        """Sikker emission af signaler på tværs af tråde"""
        if self._is_running:
            signal.emit(*args)

    def extract_text_from_pdf(self):
        """Udtrækker tekst fra PDF og gemmer hver side som separat fil"""
        try:
            with open(self.pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                total_pages = len(pdf_reader.pages)
                logging.info(f"PDF indeholder {total_pages} sider")
                
                if total_pages == 0:
                    self.status.emit("PDF-filen indeholder ingen sider.")
                    logging.warning("PDF-filen indeholder ingen sider")
                    QMessageBox.warning(None, "PDF Fejl", "PDF-filen indeholder ingen sider.")
                    return []

                # Opret output mappe
                output_dir = Path(os.path.dirname(self.pdf_path)) / "extracted_pages"
                output_dir.mkdir(exist_ok=True)
                logging.info(f"Oprettet output mappe: {output_dir}")

                return self.process_pdf_pages(pdf_reader, output_dir, self.pdf_path)
                
        except Exception as e:
            logging.error(f"Fejl ved åbning af PDF: {e}")
            self.status.emit(f"Fejl ved åbning af PDF: {e}")
            QMessageBox.critical(None, "Fejl ved åbning af PDF",
                               f"Der opstod en fejl ved åbning af PDF-filen:\n{e}")
            return []

    def process_pdf_pages(self, pdf_reader, output_dir, filename):
        """Behandler hver side i PDF'en og gemmer dem som separate filer"""
        try:
            all_text = ""
            pages_content = []  # Liste til at gemme side information
            total_pages = len(pdf_reader.pages)
            
            for page_num, page in enumerate(pdf_reader.pages, 1):
                text = page.extract_text()
                all_text += text
                
                # Gem den aktuelle sides tekst
                page_file = output_dir / f"{Path(filename).stem}_page_{page_num}.txt"
                with open(page_file, 'w', encoding='utf-8') as txt_file:
                    txt_file.write(text)
                
                # Gem side information
                pages_content.append({
                    'text': text,
                    'page_num': page_num,
                    'file_path': str(page_file)
                })
                
                # Opdater progress
                self.progress.emit(int((page_num / total_pages) * 25))
                logging.info(f"Side {page_num} gemt til {page_file}")
                
            # Gem den komplette tekst
            complete_file = output_dir / f"{Path(filename).stem}_complete.txt"
            with open(complete_file, 'w', encoding='utf-8') as txt_file:
                txt_file.write(all_text)
            
            logging.info(f"Komplet tekst gemt til {complete_file}")
            return pages_content
            
        except Exception as e:
            logging.error(f"Fejl under behandling af PDF sider: {str(e)}")
            raise

    def save_to_database(self, structured_data):
        conn = sqlite3.connect(self.db_path)
        df = pd.DataFrame(structured_data)
        try:
            df.to_sql('products', conn, if_exists='append', index=False)
        except sqlite3.OperationalError as e:
            logging.error(f"Fejl ved gemning til database: {e}")
            logging.info("Prøver at tilføje manglende kolonner...")
            cursor = conn.cursor()
            for column in df.columns:
                try:
                    cursor.execute(f'ALTER TABLE products ADD COLUMN "{column}" TEXT')
                    logging.info(f"Kolonne '{column}' tilføjet til databasen.")
                except sqlite3.OperationalError:
                    pass
            conn.commit()
            df.to_sql('products', conn, if_exists='append', index=False)
        except Exception as e:
            logging.error(f"Uventet fejl ved gemning til database: {e}")
            QMessageBox.critical(None, "Database Fejl",
                                 f"Der opstod en fejl ved gemning til databasen:\n{e}\n\n"
                                 f"En logfil er blevet gemt i {get_app_data_dir()}\n"
                                 f"Venligst send denne logfil til support for hjælp.")
        finally:
            conn.close()

    def run(self):
        try:
            self.safe_emit(self.status, "Ekstraherer tekst fra PDF...")
            pages_content = self.extract_text_from_pdf()
            if not pages_content or not self._is_running:
                self.safe_emit(self.finished)
                return

            # Hent API nøgle
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                raise Exception("OpenAI API nøgle ikke fundet. Konfigurer venligst API nøglen i indstillinger.")
            
            client = OpenAI(api_key=api_key)
            
            all_products = []
            total_pages = len(pages_content)
            progress_per_page = 70 / total_pages

            for page_data in pages_content:
                if not self._is_running:
                    break

                page_num = page_data['page_num']
                self.safe_emit(self.status, f"Analyserer side {page_num} af {total_pages} med AI...")
                logging.info(f"Starter AI analyse af side {page_num}")
                
                try:
                    result = extract_products_with_gpt(page_data['text'], client)
                    if result and 'products' in result:
                        products = result['products']
                        logging.info(f"Fandt {len(products)} produkter på side {page_num}")
                        
                        for product in products:
                            product['PDF Source'] = f"{self.pdf_name} (Side {page_num})"
                        
                        all_products.extend(products)
                        self.total_products += len(products)
                        
                    self.safe_emit(self.status, 
                        f"Side {page_num}: Fundet {len(result.get('products', []))} produkter. Total: {self.total_products}")
                    
                except Exception as e:
                    logging.error(f"Fejl ved behandling af side {page_num}: {str(e)}")
                    self.safe_emit(self.error, f"Fejl ved analyse af side {page_num}:\n{str(e)}")
                
                self.safe_emit(self.progress, 25 + int(progress_per_page * page_num))

            if all_products and self._is_running:
                self.safe_emit(self.status, f"Gemmer {self.total_products} produkter i database...")
                logging.info(f"Gemmer total {self.total_products} produkter i database")
                self.save_to_database(all_products)
                self.safe_emit(self.progress, 100)
                self.safe_emit(self.status, f"PDF-behandling fuldført. {self.total_products} produkter tilføjet.")
                self.safe_emit(self.info, "Behandling fuldført", 
                    f"PDF behandlet og {self.total_products} produkter tilføjet til databasen")
            else:
                self.safe_emit(self.status, "Ingen produkter fundet i PDF'en.")
                logging.warning("Ingen produkter fundet i PDF'en")
                self.safe_emit(self.info, "Ingen produkter fundet",
                    "Der blev ikke fundet nogen produkter med udløbsdato i PDF-filen.")
                
        except Exception as e:
            logging.error(f"PDF behandlingsfejl: {str(e)}")
            self.safe_emit(self.error, f"Der opstod en fejl under behandling af PDF'en:\n{str(e)}")
        finally:
            self._is_running = False
            self.safe_emit(self.finished)


class EditRowDialog(QDialog):
    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.setWindowTitle("Rediger/Tilføj produkt")
        self.setMinimumWidth(400)
        layout = QFormLayout()

        self.fields = []
        for label in ["ProductID", "SKU", "Article Description Batch", "Expiry Date", 
                     "EAN Serial No", "Remark", "Order QTY", "Ship QTY", "UOM", "PDF Source"]:
            line_edit = QLineEdit(data.get(label, "") if data else "")
            if label == "Expiry Date":
                line_edit.setPlaceholderText("DD.MM.YYYY")
            layout.addRow(label, line_edit)
            self.fields.append((label, line_edit))

        buttons = QHBoxLayout()
        save_button = QPushButton("Gem")
        save_button.clicked.connect(self.validate_and_accept)
        cancel_button = QPushButton("Annuller")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(save_button)
        buttons.addWidget(cancel_button)

        layout.addRow(buttons)
        self.setLayout(layout)

    def validate_and_accept(self):
        data = self.get_data()
        errors = []

        if not data.get("Article Description Batch", "").strip():
            errors.append("Feltet 'Article Description Batch' må ikke være tomt.")

        expiry_date = data.get("Expiry Date", "").strip()
        if not self.validate_date_format(expiry_date):
            errors.append("Ugyldigt datoformat for 'Expiry Date'. Formatet skal være DD.MM.YYYY.")

        if errors:
            QMessageBox.warning(self, "Valideringsfejl", "\n".join(errors))
        else:
            self.accept()

    def validate_date_format(self, date_string):
        pattern = r'^\d{2}\.\d{2}\.\d{4}$'
        if not re.match(pattern, date_string):
            return False
        try:
            datetime.strptime(date_string, '%d.%m.%Y')
            return True
        except ValueError:
            return False

    def get_data(self):
        return {label: field.text() for label, field in self.fields}


class TruncatedItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        if index.column() in [2, 3]:
            text = index.data(Qt.DisplayRole)
            if text:
                metrics = QFontMetrics(option.font)
                elidedText = metrics.elidedText(text, Qt.ElideRight, option.rect.width() - 5)
                option.text = elidedText
        super().paint(painter, option, index)

    def helpEvent(self, event, view, option, index):
        if event.type() == QEvent.ToolTip and index.column() in [2, 3]:
            QToolTip.showText(event.globalPos(), index.data(Qt.DisplayRole))
            return True
        return super().helpEvent(event, view, option, index)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # Konfigurerer vinduets ikon, titel, geometri osv.
        self.setWindowIcon(QIcon(resource_path('sweetspot_logo.ico')))
        self.setWindowTitle(config.WINDOW_TITLE)
        self.setGeometry(100, 100, config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
        user_data_dir = get_app_data_dir()
        self.db_path = os.path.join(user_data_dir, 'products.db')
        self.dropbox_auth = SecureDropboxAuth()
        self.dbx_client = None

        self.DATE_COLUMN_INDEX = -1
        self.model = QStandardItemModel()
        self.threads = []

        # Menu bar oprettes allerede i setup_ui()
        self.setup_ui()               # Her oprettes menulinjen inklusive "Fil" menuen
        self.set_style()
        self.initialize_database()
        self.ensure_local_database()
        self.load_existing_data()
        self.initialize_dropbox_client()
        self.undo_stack = []

    def get_column_index(self, column_name):
        for col in range(self.model.columnCount()):
            header_text = self.model.headerData(col, Qt.Horizontal)
            if header_text.lower() == column_name.lower():
                return col
        return -1

    def create_empty_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            UniqueID INTEGER PRIMARY KEY AUTOINCREMENT,
            ProductID TEXT,
            SKU TEXT,
            "Article Description Batch" TEXT,
            "Expiry Date" TEXT,
            "EAN Serial No" TEXT,
            Remark TEXT,
            "Order QTY" TEXT,
            "Ship QTY" TEXT,
            UOM TEXT,
            "PDF Source" TEXT
        )
        ''')
        conn.commit()
        conn.close()
        logging.info(f"Tom database oprettet: {self.db_path}")

    def sort_table(self, column_index):
        header = self.table_view.horizontalHeader()
        current_order = header.sortIndicatorOrder()
        current_section = header.sortIndicatorSection()

        if current_section == column_index:
            new_order = Qt.DescendingOrder if current_order == Qt.AscendingOrder else Qt.AscendingOrder
        else:
            new_order = Qt.AscendingOrder

        self.proxy_model.sort(column_index, new_order)

    def set_style(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
            }
            QLabel {
                font-size: 14px;
                color: #333333;
            }
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                padding: 5px 10px;
                margin: 2px;
                border-radius: 3px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #3a80d2;
            }
            QPushButton:pressed {
                background-color: #2a70c2;
            }
            QTableView {
                background-color: white;
                alternate-background-color: #f9f9f9;
                selection-background-color: #4a90e2;
                selection-color: white;
                border: 1px solid #d0d0d0;
            }
            QHeaderView::section {
                background-color: #e0e0e0;
                color: #333333;
                padding: 5px;
                border: 1px solid #d0d0d0;
            }
            QLineEdit, QComboBox {
                padding: 3px;
                border: 1px solid #d0d0d0;
                border-radius: 2px;
            }
            QProgressBar {
                border: 1px solid #d0d0d0;
                border-radius: 3px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #4a90e2;
                width: 10px;
            }
            QStatusBar {
                background-color: #e0e0e0;
                color: #333333;
            }
        """)

        self.undo_button.setStyleSheet("""
            QPushButton {
                background-color: #ff9800;
                color: white;
            }
            QPushButton:hover {
                background-color: #f57c00;
            }
            QPushButton:pressed {
                background-color: #e65100;
            }
        """)

        font = self.table_view.font()
        font.setPointSize(11)
        self.table_view.setFont(font)

        header = self.table_view.horizontalHeader()
        header.setDefaultSectionSize(120)
        header.setMinimumSectionSize(60)

    def setup_ui(self):
        main_layout = QVBoxLayout()

        # Tilføj en menulinje
        menu_bar = QMenuBar(self)
        self.setMenuBar(menu_bar)

        file_menu = menu_bar.addMenu("Fil")
        help_menu = menu_bar.addMenu("Hjælp")

        open_logs_action = QAction("Åbn logmappe", self)
        open_logs_action.triggered.connect(self.open_log_folder)
        help_menu.addAction(open_logs_action)

        export_logs_action = QAction("Eksporter logfiler", self)
        export_logs_action.triggered.connect(self.export_log_files)
        help_menu.addAction(export_logs_action)

        settings_menu = menu_bar.addMenu("Indstillinger")
        api_key_action = QAction("Konfigurer API Nøgle", self)
        api_key_action.triggered.connect(self.show_api_key_dialog)
        settings_menu.addAction(api_key_action)

        welcome_label = QLabel("Velkommen til Nordisk Film Biografers Sweetspot Data Håndtering")
        welcome_label.setStyleSheet("font-size: 28px; font-weight: bold; margin-bottom: 15px; color: #4A6D8C;")
        main_layout.addWidget(welcome_label)

        instructions_label = QLabel("Dette program hjælper dig med at håndtere produktdata fra PDF-filer og synkronisere med Dropbox.")
        instructions_label.setWordWrap(True)
        main_layout.addWidget(instructions_label)

        button_layout = QHBoxLayout()

        self.upload_pdf_button = QPushButton("1. Upload PDF-fil")
        self.upload_pdf_button.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
        self.upload_pdf_button.setToolTip("Klik her for at vælge en PDF-fil med produktdata")
        self.upload_pdf_button.clicked.connect(self.upload_pdf)
        button_layout.addWidget(self.upload_pdf_button)

        self.upload_to_dropbox_button = QPushButton("2. Synkroniser med Dropbox")
        self.upload_to_dropbox_button.setIcon(QIcon(resource_path("dropbox_icon.png")))
        self.upload_to_dropbox_button.setToolTip("Klik her for at uploade databasen til Dropbox")
        self.upload_to_dropbox_button.clicked.connect(self.upload_to_dropbox)
        self.upload_to_dropbox_button.setEnabled(False)
        button_layout.addWidget(self.upload_to_dropbox_button)

        self.download_from_dropbox_button = QPushButton("3. Hent database fra Dropbox")
        self.download_from_dropbox_button.setIcon(QIcon(resource_path("dropbox_icon.png")))
        self.download_from_dropbox_button.setToolTip("Klik her for at hente den seneste database fra Dropbox")
        self.download_from_dropbox_button.clicked.connect(self.download_from_dropbox)
        self.download_from_dropbox_button.setEnabled(False)
        button_layout.addWidget(self.download_from_dropbox_button)

        self.undo_button = QPushButton("Fortryd")
        self.undo_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowBack))
        self.undo_button.setToolTip("Klik her for at fortryde den seneste handling")
        self.undo_button.clicked.connect(self.undo_last_action)
        self.undo_button.setEnabled(False)
        button_layout.addWidget(self.undo_button)

        self.add_row_button = QPushButton("Tilføj række")
        self.add_row_button.setIcon(self.style().standardIcon(QStyle.SP_FileDialogNewFolder))
        self.add_row_button.setToolTip("Klik her for at tilføje en ny produktrække manuelt")
        self.add_row_button.clicked.connect(self.add_row_manually)
        button_layout.addWidget(self.add_row_button)

        main_layout.addLayout(button_layout)

        progress_layout = QHBoxLayout()
        progress_layout.addStretch()
        self.progress_label = QLabel("0%")
        progress_layout.addWidget(self.progress_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedSize(100, 20)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #4A6D8C;
                border-radius: 3px;
                background-color: white;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #4A6D8C;
            }
        """)
        progress_layout.addWidget(self.progress_bar)
        main_layout.addLayout(progress_layout)

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filtrer produkter:"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["Alle", "UniqueID", "ProductID", "SKU", "Article Description Batch", "Expiry Date",
                                    "EAN Serial No", "Remark", "Order QTY", "Ship QTY", "UOM", "PDF Source"])
        self.filter_combo.setToolTip("Vælg hvilken kolonne du vil filtrere efter")
        filter_layout.addWidget(self.filter_combo)

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Indtast søgeord her...")
        self.filter_input.setToolTip("Indtast tekst for at filtrere produktlisten")
        self.filter_input.textChanged.connect(self.apply_filter)
        filter_layout.addWidget(self.filter_input)

        main_layout.addLayout(filter_layout)

        table_label = QLabel("Produktoversigt:")
        main_layout.addWidget(table_label)

        self.table_view = QTableView()
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSelectionBehavior(QTableView.SelectRows)
        self.table_view.setStyleSheet("QTableView { border: 1px solid #ddd; } QTableView::item { padding: 5px; }")
        self.table_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self.show_context_menu)

        delegate = TruncatedItemDelegate(self.table_view)
        self.table_view.setItemDelegate(delegate)

        main_layout.addWidget(self.table_view)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        self.proxy_model = DateSortFilterProxyModel(self.DATE_COLUMN_INDEX)
        self.proxy_model.setSourceModel(self.model)
        self.table_view.setModel(self.proxy_model)
        self.table_view.setSortingEnabled(True)
        self.table_view.horizontalHeader().setSectionsClickable(True)
        self.table_view.horizontalHeader().sectionClicked.connect(self.sort_table)

        self.statusBar().showMessage("Klar")

        # Tilføj Upload-undermenu til Fil-menuen
        # Opret en undermenu til upload-funktioner
        upload_menu = QMenu("Upload", self)
        
        # Upload PDF action: Denne funktionalitet tillader upload og analyse af en PDF-fil
        upload_pdf_action = QAction("Upload PDF-fil", self)
        upload_pdf_action.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))  # Brug system PDF ikon
        upload_pdf_action.setStatusTip("Upload og analyser en PDF-fil")
        upload_pdf_action.triggered.connect(self.handle_pdf_upload)
        upload_menu.addAction(upload_pdf_action)
        
        # Upload billede action: Denne funktionalitet tillader upload og analyse af et billede af en udløbsdatoliste
        upload_image_action = QAction("Upload Udløbsdatoliste (Billede)", self)
        upload_image_action.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))  # Brug system billede ikon
        upload_image_action.setStatusTip("Upload og analyser et billede af en udløbsdatoliste")
        upload_image_action.triggered.connect(self.handle_image_upload)
        upload_menu.addAction(upload_image_action)
        
        # Tilføj Upload-undermenuen til Fil-menuen
        file_menu.addMenu(upload_menu)
        # Tilføj en separator for at adskille upload-funktionerne fra database-handlingerne
        file_menu.addSeparator()
        
        # Database-handlings actions:
        # Action for at rydde hele databasen. Backup oprettes først for sikkerhed.
        clear_db_action = QAction("Ryd Database", self)
        clear_db_action.setStatusTip("Ryd hele databasen (opretter backup først)")
        clear_db_action.triggered.connect(self.clear_database)
        file_menu.addAction(clear_db_action)
        
        # Action for at oprette en ny, tom database. Først laves der backup af den nuværende database.
        create_empty_db_action = QAction("Opret Tom Database", self)
        create_empty_db_action.setStatusTip("Opret en ny tom database")
        create_empty_db_action.triggered.connect(self.create_new_empty_database)
        file_menu.addAction(create_empty_db_action)

        # Tilføj nedenfor en ny action til Multi-upload:
        multi_upload_action = QAction("Upload Flere Filer", self)
        multi_upload_action.setToolTip("Upload flere filer i kø")
        multi_upload_action.triggered.connect(self.upload_multiple)
        file_menu.addAction(multi_upload_action)

    def open_log_folder(self):
        log_dir = get_app_data_dir()
        QDesktopServices.openUrl(QUrl.fromLocalFile(log_dir))

    def export_log_files(self):
        log_dir = get_app_data_dir()
        log_file = os.path.join(log_dir, 'sweetspot.log')
        if os.path.exists(log_file):
            save_path, _ = QFileDialog.getSaveFileName(self, "Gem logfil som", "sweetspot.log", "Log Files (*.log)")
            if save_path:
                try:
                    shutil.copy2(log_file, save_path)
                    QMessageBox.information(self, "Logfiler eksporteret", f"Logfilen er blevet gemt til {save_path}")
                except Exception as e:
                    QMessageBox.critical(self, "Fejl", f"Kunne ikke eksportere logfilen: {e}")
        else:
            QMessageBox.warning(self, "Ingen logfil", "Ingen logfil blev fundet.")

    def initialize_database(self):
        if not os.path.exists(self.db_path):
            self.create_empty_database()
        else:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='products';")
            result = cursor.fetchone()
            if result is None:
                logging.info("Table 'products' is missing in the database. Creating the table.")
                self.create_empty_database()
            else:
                cursor.execute("PRAGMA table_info(products)")
                columns_info = cursor.fetchall()
                columns = [info[1] for info in columns_info]
                columns_lower = [col.lower() for col in columns]
                has_uniqueid = any(info[1].lower() == 'uniqueid' and info[5] == 1 for info in columns_info)
                if not has_uniqueid:
                    logging.info("Migrating database to add 'UniqueID' primary key and resolve column conflicts.")
                    QMessageBox.information(self, "Database Opdatering",
                                            "Din lokale database opdateres til det nye format. Dette kan tage et øjeblik.")
                    cursor.execute('ALTER TABLE products RENAME TO products_old')
                    cursor.execute('''
                    CREATE TABLE products (
                        UniqueID INTEGER PRIMARY KEY AUTOINCREMENT,
                        ProductID TEXT,
                        SKU TEXT,
                        "Article Description Batch" TEXT,
                        "Expiry Date" TEXT,
                        "EAN Serial No" TEXT,
                        Remark TEXT,
                        "Order QTY" TEXT,
                        "Ship QTY" TEXT,
                        UOM TEXT,
                        "PDF Source" TEXT
                    )
                    ''')
                    old_to_new_columns = {}
                    for info in columns_info:
                        old_col = info[1]
                        if old_col.lower() == 'id':
                            old_to_new_columns[old_col] = 'ProductID'
                        elif old_col in ['ProductID', 'SKU', "Article Description Batch", "Expiry Date", "EAN Serial No",
                                         "Remark", "Order QTY", "Ship QTY", "UOM", "PDF Source"]:
                            old_to_new_columns[old_col] = old_col
                        else:
                            pass
                    old_columns = list(old_to_new_columns.keys())
                    new_columns = list(old_to_new_columns.values())
                    columns_str_old = ', '.join(f'"{col}"' for col in old_columns)
                    columns_str_new = ', '.join(f'"{col}"' for col in new_columns)
                    cursor.execute(f'INSERT INTO products ({columns_str_new}) SELECT {columns_str_old} FROM products_old')
                    cursor.execute('DROP TABLE products_old')
                    conn.commit()
                    logging.info("Migration completed.")
                else:
                    required_columns = ["ProductID", "SKU", "Article Description Batch", "Expiry Date", "EAN Serial No",
                                        "Remark", "Order QTY", "Ship QTY", "UOM", "PDF Source"]
                    existing_columns = columns
                    missing_columns = [col for col in required_columns if col not in existing_columns]
                    for col in missing_columns:
                        cursor.execute(f'ALTER TABLE products ADD COLUMN "{col}" TEXT')
                        logging.info(f"Kolonne '{col}' tilføjet til eksisterende tabel.")
                    conn.commit()
            conn.close()

    def ensure_local_database(self):
        if not os.path.exists(self.db_path):
            self.create_empty_database()
            QMessageBox.information(self, "Ny database oprettet",
                                    "En ny, tom database er blevet oprettet lokalt. "
                                    "Du kan nu begynde at tilføje data eller hente en eksisterende database fra Dropbox.")

    def initialize_dropbox_client(self):
        self.dbx_client = self.dropbox_auth.get_dropbox_client()
        if self.dbx_client is None:
            QMessageBox.warning(self, "Dropbox Fejl", "Dropbox-klient ikke initialiseret. Kontroller dine indstillinger i config.py.")
            self.upload_to_dropbox_button.setEnabled(False)
            self.download_from_dropbox_button.setEnabled(False)
        else:
            self.upload_to_dropbox_button.setEnabled(True)
            self.download_from_dropbox_button.setEnabled(True)

    def upload_pdf(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Vælg PDF-fil med produktdata", "", "PDF Filer (*.pdf)")
        if file_path:
            self.statusBar().showMessage(f"Behandler fil: {os.path.basename(file_path)}")
            self.processor = PDFProcessor(file_path, self.db_path)
            
            # Tilføj signal connections
            self.processor.progress.connect(self.update_progress)
            self.processor.status.connect(self.update_status)
            self.processor.finished.connect(self.on_pdf_processing_finished)
            self.processor.error.connect(self.show_error)
            self.processor.info.connect(self.show_info)
            
            self.processor.start()
            self.threads.append(self.processor)

    def show_error(self, message):
        QMessageBox.critical(self, "Fejl", message)

    def show_info(self, title, message):
        QMessageBox.information(self, title, message)

    def on_pdf_processing_finished(self):
        self.load_existing_data()
        self.update_status_bar()
        QMessageBox.information(self, "PDF Behandling", "PDF-behandling fuldført. Du kan nu synkronisere med Dropbox.")
        self.upload_to_dropbox_button.setEnabled(True)

    def update_progress(self, value):
        self.progress_bar.setValue(value)
        self.progress_label.setText(f"{value}%")

    def update_status(self, message):
        self.statusBar().showMessage(message)

    def load_existing_data(self):
        conn = sqlite3.connect(self.db_path)
        try:
            df = pd.read_sql_query("SELECT * FROM products", conn)
            df = df.fillna('')
            df.columns = [col if col.lower() != 'uniqueid' else 'UniqueID' for col in df.columns]
        except pd.io.sql.DatabaseError:
            df = pd.DataFrame(columns=["UniqueID", "ProductID", "SKU", "Article Description Batch", "Expiry Date",
                                       "EAN Serial No", "Remark", "Order QTY", "Ship QTY", "UOM", "PDF Source"])
        finally:
            conn.close()
        self.update_table(df)

    def update_table(self, df):
        self.model.clear()
        if not df.empty:
            if 'UniqueID' not in df.columns:
                df.reset_index(inplace=True)
                df.rename(columns={'index': 'UniqueID'}, inplace=True)

            if 'UniqueID' in df.columns and df.columns[0] != 'UniqueID':
                cols = df.columns.tolist()
                cols.insert(0, cols.pop(cols.index('UniqueID')))
                df = df[cols]

            headers = list(df.columns)

            if "Expiry Date" in headers:
                self.DATE_COLUMN_INDEX = headers.index("Expiry Date")
                self.proxy_model.date_column_index = self.DATE_COLUMN_INDEX
            else:
                self.DATE_COLUMN_INDEX = -1
                self.proxy_model.date_column_index = self.DATE_COLUMN_INDEX

            self.model.setHorizontalHeaderLabels(headers)

            for _, row in df.iterrows():
                items = []
                for column in headers:
                    item = QStandardItem(str(row[column]))
                    if column in ["SKU", "Article Description Batch"]:
                        item.setToolTip(str(row[column]))
                    if column == "Expiry Date":
                        try:
                            expiry_date = datetime.strptime(row[column], "%d.%m.%Y")
                            today = datetime.now()
                            days_until_expiry = (expiry_date - today).days

                            if days_until_expiry <= 0:
                                item.setBackground(QBrush(QColor(255, 0, 0, 100)))
                            elif days_until_expiry <= 14:
                                item.setBackground(QBrush(QColor(255, 165, 0, 100)))
                            elif days_until_expiry <= 30:
                                item.setBackground(QBrush(QColor(255, 255, 0, 100)))
                        except ValueError:
                            item.setBackground(QBrush(QColor(255, 0, 0, 100)))
                            logging.error(f"Fejl ved parsing af dato: {row[column]} for Article Description Batch: {row['Article Description Batch']}")

                            QMessageBox.warning(
                                self,
                                "Ugyldig dato",
                                f"Ugyldig dato fundet: {row[column]} for produkt: {row['Article Description Batch']}\n"
                                f"Venligst ret datoen til formatet DD.MM.YYYY."
                            )
                    items.append(item)
                self.model.appendRow(items)

        self.table_view.resizeColumnsToContents()
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        if self.DATE_COLUMN_INDEX != -1:
            self.table_view.sortByColumn(self.DATE_COLUMN_INDEX, Qt.AscendingOrder)
        else:
            self.table_view.sortByColumn(0, Qt.AscendingOrder)

        self.update_status_bar()

    def apply_filter(self):
        filter_text = self.filter_input.text()
        filter_column = self.filter_combo.currentText()

        if filter_column == "Alle":
            self.proxy_model.setFilterKeyColumn(-1)
        else:
            column_index = -1

            for i in range(self.model.columnCount()):
                if self.model.headerData(i, Qt.Horizontal) == filter_column:
                    column_index = i
                    break
            if column_index == -1:
                logging.error(f"Filterkolonne ikke fundet: {filter_column}")
                QMessageBox.warning(self, "Filter Fejl", f"Kolonnen '{filter_column}' blev ikke fundet.")
                return

            self.proxy_model.setFilterKeyColumn(column_index)

        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy_model.setFilterRegularExpression(filter_text)

    def add_row_manually(self):
        dialog = EditRowDialog(self)
        if dialog.exec_():
            new_data = dialog.get_data()
            try:
                last_id = self.perform_critical_operation(self.add_to_database, new_data)
                self.load_existing_data()
                QMessageBox.information(self, "Produkt tilføjet", f"Nyt produkt med SKU {new_data['SKU']} er blevet tilføjet.")
                self.add_to_undo_stack("add_row", last_id)
            except Exception as e:
                QMessageBox.critical(self, "Fejl", f"Der opstod en fejl ved tilføjelse af rækken: {str(e)}\n\n"
                                                   f"En logfil er blevet gemt i {get_app_data_dir()}\n"
                                                   f"Venligst send denne logfil til support for hjælp.")

    def add_to_database(self, data, include_id=False):
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            if not include_id and 'UniqueID' in data:
                del data['UniqueID']
            columns = list(data.keys())
            placeholders = ', '.join('?' for _ in columns)
            column_names = ', '.join(f'"{col}"' for col in columns)
            sql = f'INSERT INTO products ({column_names}) VALUES ({placeholders})'
            cursor.execute(sql, tuple(data.values()))
            conn.commit()
            last_id = cursor.lastrowid
            return last_id
        except sqlite3.Error as e:
            conn.rollback()
            logging.error(f"Database fejl: {str(e)}")
            raise
        finally:
            conn.close()

    def upload_to_dropbox(self):
        if not self.dbx_client:
            QMessageBox.warning(self, "Fejl", "Dropbox-klient ikke tilgængelig. Kontroller dine indstillinger.")
            return

        reply = QMessageBox.question(self, 'Bekræft upload',
                                     "Er du sikker på, at du vil uploade databasen til Dropbox?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.upload_to_dropbox_button.setEnabled(False)
            self.statusBar().showMessage("Uploader til Dropbox...")

            backup_path = self.create_backup()

            try:
                self.dropbox_sync = DropboxSync(self.db_path, self.dbx_client)
                self.dropbox_sync.status.connect(self.update_status)
                self.dropbox_sync.finished.connect(self.on_dropbox_upload_finished)
                self.dropbox_sync.start()
                self.threads.append(self.dropbox_sync)
                self.add_to_undo_stack("upload_to_dropbox")
            except Exception as e:
                logging.error(f"Fejl under upload til Dropbox: {str(e)}")
                QMessageBox.critical(self, "Fejl", f"Der opstod en fejl under upload: {str(e)}\n\n"
                                                   f"En logfil er blevet gemt i {get_app_data_dir()}\n"
                                                   f"Venligst send denne logfil til support for hjælp.")
                if backup_path:
                    self.restore_from_backup(backup_path)
            finally:
                self.upload_to_dropbox_button.setEnabled(True)

    def create_backup(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(get_app_data_dir(), 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        backup_path = os.path.join(backup_dir, f'products_backup_{timestamp}.db')
        shutil.copy2(self.db_path, backup_path)
        logging.info(f"Backup oprettet: {backup_path}")
        self.statusBar().showMessage(f"Backup oprettet: {backup_path}")
        return backup_path

    def restore_from_backup(self, backup_path):
        if backup_path and os.path.exists(backup_path):
            try:
                shutil.copy2(backup_path, self.db_path)
                logging.info("Database gendannet fra backup")
                self.load_existing_data()
            except Exception as e:
                logging.error(f"Fejl ved gendannelse fra backup: {str(e)}")
                QMessageBox.critical(self, "Backup Fejl", "Der opstod en fejl ved gendannelse fra backup. Kontakt venligst support.")
        else:
            logging.error("Ingen gyldig backup-fil fundet")

    def perform_critical_operation(self, operation, *args):
        backup_path = self.create_backup()
        try:
            result = operation(*args)
            return result
        except Exception as e:
            if backup_path:
                self.restore_from_backup(backup_path)
            raise e

    def execute_db_operation(self, operation, args=()):
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            conn.execute('BEGIN')
            cursor.execute(operation, args)
            conn.commit()
            return cursor.fetchall()
        except sqlite3.Error as e:
            conn.rollback()
            logging.error(f"Database fejl: {str(e)}")
            raise
        finally:
            conn.close()

    def on_dropbox_upload_finished(self):
        self.upload_to_dropbox_button.setEnabled(True)
        QMessageBox.information(self, "Dropbox Upload", "Upload til Dropbox fuldført.")
        self.update_status_bar()

    def download_from_dropbox(self):
        if not self.dbx_client:
            QMessageBox.warning(self, "Fejl", "Dropbox-klient ikke tilgængelig. Kontroller dine indstillinger.")
            return

        reply = QMessageBox.question(self, 'Bekræft download',
                                    "Er du sikker på, at du vil hente databasen fra Dropbox? Dette vil overskrive din lokale database.",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.download_from_dropbox_button.setEnabled(False)
            self.statusBar().showMessage("Henter database fra Dropbox...")

            backup_path = self.create_backup()

            try:
                _, response = self.dbx_client.files_download("/products.db")
                data = response.content

                temp_db_path = self.db_path + ".temp"
                with open(temp_db_path, "wb") as temp_file:
                    temp_file.write(data)

                self.close_database_connection()

                os.replace(temp_db_path, self.db_path)

                self.initialize_database()
                self.statusBar().showMessage("Database hentet fra Dropbox og opdateret lokalt.")
                self.load_existing_data()
                QMessageBox.information(self, "Dropbox Download", "Download fra Dropbox fuldført og lokal database opdateret.")
                self.add_to_undo_stack("download_from_dropbox", backup_path)
            except dropbox.exceptions.AuthError as e:
                error_msg = "Autentificeringsfejl med Dropbox. Kontroller din adgangstoken."
                logging.error(f"Dropbox autentificeringsfejl: {e}")
                QMessageBox.critical(self, "Dropbox Fejl", error_msg)
                if backup_path:
                    self.restore_from_backup(backup_path)
            except dropbox.exceptions.HttpError as e:
                error_msg = "Netværksfejl. Kontroller din internetforbindelse."
                logging.error(f"Dropbox netværksfejl: {e}")
                QMessageBox.critical(self, "Netværksfejl", error_msg)
                if backup_path:
                    self.restore_from_backup(backup_path)
            except Exception as e:
                error_msg = f"Der opstod en fejl ved hentning af databasen: {e}"
                logging.error(f"Fejl ved hentning af databasen fra Dropbox: {e}")
                QMessageBox.critical(self, "Fejl", error_msg)
                if backup_path:
                    self.restore_from_backup(backup_path)
            finally:
                self.download_from_dropbox_button.setEnabled(True)
                self.update_status_bar()

    def close_database_connection(self):
        # Hvis du har en vedvarende databaseforbindelse, skal du lukke den her
        pass

    def show_context_menu(self, pos):
        index = self.table_view.indexAt(pos)
        if index.isValid():
            menu = QMenu(self)
            edit_action = QAction("Rediger produkt", self)
            edit_action.triggered.connect(lambda: self.edit_row(index))
            delete_action = QAction("Slet produkt", self)
            delete_action.triggered.connect(lambda: self.delete_row(index))
            menu.addAction(edit_action)
            menu.addAction(delete_action)
            menu.exec_(self.table_view.viewport().mapToGlobal(pos))

    def edit_row(self, index):
        source_index = self.proxy_model.mapToSource(index)
        row = source_index.row()

        id_column_index = self.get_column_index('UniqueID')
        if id_column_index == -1:
            logging.error("UniqueID kolonne ikke fundet i modellen")
            QMessageBox.critical(self, "Fejl", "UniqueID kolonne ikke fundet. Kan ikke redigere produktet.")
            return

        row_id = self.model.item(row, id_column_index).text()
        if not row_id:
            logging.error("UniqueID ikke fundet for den valgte række")
            QMessageBox.critical(self, "Fejl", "UniqueID ikke fundet for det valgte produkt. Kan ikke redigere produktet.")
            return

        data = {}
        for col in range(self.model.columnCount()):
            header_text = self.model.headerData(col, Qt.Horizontal)
            data[header_text] = self.model.item(row, col).text()

        dialog = EditRowDialog(self, data)
        if dialog.exec_():
            new_data = dialog.get_data()
            try:
                self.perform_critical_operation(self.update_database_row, row_id, new_data)
                self.load_existing_data()
                self.statusBar().showMessage(f"Produkt er blevet opdateret.")
                self.add_to_undo_stack("edit_row", row_id, data)
            except Exception as e:
                QMessageBox.critical(self, "Fejl", f"Der opstod en fejl ved redigering af produktet: {str(e)}\n\n"
                                                   f"En logfil er blevet gemt i {get_app_data_dir()}\n"
                                                   f"Venligst send denne logfil til support for hjælp.")

    def delete_row(self, index):
        source_index = self.proxy_model.mapToSource(index)
        row = source_index.row()

        id_column_index = self.get_column_index('UniqueID')
        if id_column_index == -1:
            logging.error("UniqueID kolonne ikke fundet i modellen")
            QMessageBox.critical(self, "Fejl", "UniqueID kolonne ikke fundet. Kan ikke slette produktet.")
            return

        row_id = self.model.item(row, id_column_index).text()
        if not row_id:
            logging.error("UniqueID ikke fundet for den valgte række")
            QMessageBox.critical(self, "Fejl", "UniqueID ikke fundet for det valgte produkt. Kan ikke slette produktet.")
            return

        data = {}
        for col in range(self.model.columnCount()):
            header_text = self.model.headerData(col, Qt.Horizontal)
            data[header_text] = self.model.item(row, col).text()

        reply = QMessageBox.question(
            self,
            'Bekræft sletning',
            f"Er du sikker på, at du vil slette produktet?\n\nUniqueID: {row_id}\nBeskrivelse: {data.get('Article Description Batch', '')}\nUdløbsdato: {data.get('Expiry Date', '')}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                self.perform_critical_operation(self.delete_from_database, row_id)
                self.load_existing_data()
                self.statusBar().showMessage(f"Produkt er blevet slettet.")
                self.add_to_undo_stack("delete_row", row_id, data)
            except Exception as e:
                QMessageBox.critical(self, "Fejl", f"Der opstod en fejl ved sletning af produktet: {str(e)}\n\n"
                                                   f"En logfil er blevet gemt i {get_app_data_dir()}\n"
                                                   f"Venligst send denne logfil til support for hjælp.")

    def delete_from_database(self, row_id):
        self.execute_db_operation('''
            DELETE FROM products 
            WHERE UniqueID=?
        ''', (row_id,))

    def update_database_row(self, row_id, new_data):
        columns = ["ProductID", "SKU", "Article Description Batch", "Expiry Date", "EAN Serial No",
                   "Remark", "Order QTY", "Ship QTY", "UOM", "PDF Source"]
        values = [new_data.get(col, '') for col in columns]
        self.execute_db_operation(f'''
            UPDATE products
            SET {', '.join([f'"{col}"=?' for col in columns])}
            WHERE UniqueID=?
        ''', tuple(values) + (row_id,))

    def add_to_undo_stack(self, action, *args):
        self.undo_stack.append((action, args))
        self.undo_button.setEnabled(True)

    def undo_last_action(self):
        if not self.undo_stack:
            return
        action, args = self.undo_stack.pop()
        try:
            if action == "add_row":
                self.undo_add_row(args[0])
            elif action == "edit_row":
                self.undo_edit_row(args[0], args[1])
            elif action == "delete_row":
                self.undo_delete_row(args[0], args[1])
            elif action == "upload_pdf":
                self.undo_pdf_upload(args[0])
            elif action == "upload_to_dropbox":
                self.undo_dropbox_upload()
            elif action == "download_from_dropbox":
                self.undo_download_from_dropbox(args[0])
            elif action == "clear_database":
                self.undo_clear_database(args[0])
        except Exception as e:
            logging.error(f"Fejl ved undo-handling: {str(e)}")
            QMessageBox.critical(self, "Fejl", f"Der opstod en fejl ved fortryd-handlingen: {str(e)}\n\n"
                                               f"En logfil er blevet gemt i {get_app_data_dir()}\n"
                                               f"Venligst send denne logfil til support for hjælp.")
        finally:
            self.load_existing_data()
            if not self.undo_stack:
                self.undo_button.setEnabled(False)

    def undo_add_row(self, row_id):
        self.delete_from_database(row_id)
        self.statusBar().showMessage(f"Fortryd: Fjernet nyligt tilføjet produkt")

    def undo_edit_row(self, row_id, old_data):
        self.update_database_row(row_id, old_data)
        self.statusBar().showMessage(f"Fortryd: Gendannet original data for produkt")

    def undo_delete_row(self, row_id, data):
        data['UniqueID'] = row_id
        self.add_to_database(data, include_id=True)
        self.statusBar().showMessage(f"Fortryd: Gendannet slettet produkt")

    def undo_pdf_upload(self, file_path):
        self.execute_db_operation('DELETE FROM products WHERE "PDF Source"=?', (os.path.basename(file_path),))
        self.statusBar().showMessage(f"Fortryd: Fjernet data fra PDF-fil: {os.path.basename(file_path)}")

    def undo_dropbox_upload(self):
        QMessageBox.information(self, "Fortryd Upload",
                                "Fortrydelse af Dropbox-upload er ikke mulig. Venligst upload den seneste version igen, hvis nødvendigt.")
        self.statusBar().showMessage("Fortryd: Kan ikke fortryde Dropbox-upload.")

    def undo_download_from_dropbox(self, backup_path):
        self.restore_from_backup(backup_path)
        self.statusBar().showMessage("Fortryd: Gendannet lokal database fra backup efter download fra Dropbox.")

    def undo_clear_database(self, backup_path):
        """Gendan database fra backup efter rydning"""
        if os.path.exists(backup_path):
            try:
                # Luk forbindelse til databasen
                self.close_database_connection()
                
                # Gendan fra backup
                shutil.copy2(backup_path, self.db_path)
                
                # Genindlæs data
                self.load_existing_data()
                self.statusBar().showMessage("Database gendannet fra backup")
                logging.info(f"Database gendannet fra backup: {backup_path}")
                
            except Exception as e:
                logging.error(f"Fejl ved gendannelse af database: {str(e)}")
                QMessageBox.critical(
                    self,
                    "Fejl",
                    f"Der opstod en fejl ved gendannelse af databasen:\n{str(e)}"
                )

    def update_status_bar(self):
        total_products = self.model.rowCount()
        visible_products = self.proxy_model.rowCount()
        self.statusBar().showMessage(f"Viser {visible_products} af {total_products} produkter | Sidste opdatering: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    def terminate_threads(self):
        for thread in self.threads:
            if thread.isRunning():
                thread.quit()
                thread.wait()

    def closeEvent(self, event):
        try:
            reply = QMessageBox.question(
                self,
                'Afslut program',
                "Er du sikker på, at du vil afslutte programmet?\nHusk at synkronisere med Dropbox, hvis du har lavet ændringer.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                self.terminate_threads()

                # Luk alle logging handlers
                for handler in logging.root.handlers[:]:
                    handler.close()
                    logging.root.removeHandler(handler)

                event.accept()
            else:
                event.ignore()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Fejl ved lukning",
                f"Der opstod en fejl ved lukning af programmet: {str(e)}\n\n"
                f"En logfil er blevet gemt i {get_app_data_dir()}\n"
                f"Venligst send denne logfil til support for hjælp."
            )
            event.ignore()

    def show_api_key_dialog(self):
        """Viser dialog til at indtaste API nøgle"""
        dialog = APIKeyDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            api_key = dialog.get_api_key()
            if api_key:
                self.save_api_key(api_key)
                QMessageBox.information(self, "Success", "API nøgle gemt succesfuldt!")
            else:
                QMessageBox.warning(self, "Fejl", "API nøgle må ikke være tom.")

    def save_api_key(self, api_key):
        """Gem API nøglen sikkert"""
        try:
            # Gem i .env fil
            with open('.env', 'w') as f:
                f.write(f'OPENAI_API_KEY={api_key}')
            # Opdater miljøvariabel
            os.environ['OPENAI_API_KEY'] = api_key
            logging.info("API nøgle gemt succesfuldt")
        except Exception as e:
            logging.error(f"Fejl ved gemning af API nøgle: {str(e)}")
            raise

    def create_backup_before_clear(self):
        """Opret backup af databasen før rydning"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = os.path.join(get_app_data_dir(), "backups")
            os.makedirs(backup_dir, exist_ok=True)
            
            backup_path = os.path.join(backup_dir, f"database_backup_before_clear_{timestamp}.db")
            shutil.copy2(self.db_path, backup_path)
            
            logging.info(f"Backup oprettet: {backup_path}")
            return backup_path
            
        except Exception as e:
            logging.error(f"Fejl ved oprettelse af backup: {str(e)}")
            raise

    def clear_database(self):
        """Ryd databasen efter bekræftelse og backup"""
        reply = QMessageBox.question(
            self, 
            'Bekræft sletning',
            "Er du sikker på, at du vil rydde hele databasen?\n"
            "Dette vil slette alle produkter.\n\n"
            "En backup vil blive gemt først.",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                # Opret backup først
                backup_path = self.create_backup_before_clear()
                
                # Ryd databasen
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('DELETE FROM products')
                conn.commit()
                conn.close()
                
                # Opdater visning
                self.load_existing_data()
                self.update_status_bar()
                
                # Tilføj til undo stack
                self.add_to_undo_stack("clear_database", backup_path)
                
                QMessageBox.information(
                    self,
                    "Database Ryddet",
                    f"Databasen er blevet ryddet.\n"
                    f"En backup er gemt her:\n{backup_path}"
                )
                
                logging.info("Database ryddet succesfuldt")
                
            except Exception as e:
                logging.error(f"Fejl ved rydning af database: {str(e)}")
                QMessageBox.critical(
                    self,
                    "Fejl",
                    f"Der opstod en fejl ved rydning af databasen:\n{str(e)}\n\n"
                    f"Hvis der blev oprettet en backup, kan den findes i:\n"
                    f"{get_app_data_dir()}/backups/"
                )

    def create_new_empty_database(self):
        """Opret en ny tom database efter bekræftelse"""
        reply = QMessageBox.question(
            self, 
            'Bekræft oprettelse',
            "Er du sikker på, at du vil oprette en ny tom database?\n"
            "Dette vil gemme en backup af den nuværende database først.",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                # Opret backup først
                backup_path = self.create_backup_before_clear()
                
                # Luk forbindelse til databasen
                self.close_database_connection()
                
                # Slet eksisterende database
                if os.path.exists(self.db_path):
                    os.remove(self.db_path)
                
                # Opret ny tom database
                self.create_empty_database()
                
                # Opdater visning
                self.load_existing_data()
                self.update_status_bar()
                
                # Tilføj til undo stack
                self.add_to_undo_stack("clear_database", backup_path)
                
                QMessageBox.information(
                    self,
                    "Database Oprettet",
                    f"En ny tom database er blevet oprettet.\n"
                    f"En backup af den gamle database er gemt her:\n{backup_path}"
                )
                
                logging.info("Ny tom database oprettet succesfuldt")
                
            except Exception as e:
                logging.error(f"Fejl ved oprettelse af ny database: {str(e)}")
                QMessageBox.critical(
                    self,
                    "Fejl",
                    f"Der opstod en fejl ved oprettelse af ny database:\n{str(e)}\n\n"
                    f"Hvis der blev oprettet en backup, kan den findes i:\n"
                    f"{get_app_data_dir()}/backups/"
                )

    def handle_image_upload(self):
        """Håndter upload af billede"""
        try:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Vælg billede", "", "Image Files (*.png *.jpg *.jpeg)"
            )
            if file_path:
                self.statusBar().showMessage("Behandler billede...")
                self.process_image_file(file_path)
        except Exception as e:
            logging.error(f"Fejl ved billedupload: {str(e)}")
            QMessageBox.critical(self, "Fejl", 
                f"Der opstod en fejl ved upload af billedet:\n{str(e)}")

    def process_image_file(self, image_path):
        """Behandl uploadet billede"""
        try:
            # Opret OpenAI klient
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                raise Exception("OpenAI API nøgle ikke fundet. Konfigurer venligst API nøglen i indstillinger.")
            
            client = OpenAI(api_key=api_key)
            
            # Få data fra Vision API
            json_data = extract_products_with_vision(image_path, client)
            
            # Parse JSON og konverter til database format
            products = []
            for item in json_data.get('products', []):
                product = {
                    'Article Description Batch': item['product_name'],
                    'Expiry Date': item['expiry_date'],
                    'PDF Source': f"Image: {os.path.basename(image_path)}",
                    'ProductID': '',
                    'SKU': '',
                    'EAN Serial No': '',
                    'Remark': '',
                    'Order QTY': '1',
                    'Ship QTY': '1',
                    'UOM': 'EACH'
                }
                products.append(product)
            
            if not products:
                raise Exception("Ingen produkter fundet i billedet")
            
            # Gem i database
            self.save_to_database(products)
            
            # Opdater status
            self.statusBar().showMessage(f"Tilføjet {len(products)} produkter fra billede")
            
        except Exception as e:
            logging.error(f"Fejl ved behandling af billede: {str(e)}")
            QMessageBox.critical(self, "Fejl", 
                f"Der opstod en fejl ved behandling af billedet:\n{str(e)}")

    def save_to_database(self, products):
        """Gem produkter i databasen"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            for product in products:
                cursor.execute('''
                    INSERT INTO products (
                        ProductID, SKU, "Article Description Batch", 
                        "Expiry Date", "EAN Serial No", Remark,
                        "Order QTY", "Ship QTY", UOM, "PDF Source"
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    product['ProductID'],
                    product['SKU'],
                    product['Article Description Batch'],
                    product['Expiry Date'],
                    product['EAN Serial No'],
                    product['Remark'],
                    product['Order QTY'],
                    product['Ship QTY'],
                    product['UOM'],
                    product['PDF Source']
                ))
                
            conn.commit()
            conn.close()
            
            # Opdater visning
            self.load_existing_data()
            self.update_status_bar()
            
            QMessageBox.information(self, "Success", 
                f"Gemt {len(products)} produkter i databasen")
            
        except Exception as e:
            logging.error(f"Fejl ved gemning i database: {str(e)}")
            QMessageBox.critical(self, "Fejl", 
                f"Der opstod en fejl ved gemning i databasen:\n{str(e)}")

    def close_database_connection(self):
        """Luk database forbindelse sikkert"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.close()
            logging.info("Database forbindelse lukket")
        except Exception as e:
            logging.error(f"Fejl ved lukning af database forbindelse: {str(e)}")

    def handle_pdf_upload(self):
        """Håndter upload af PDF fil"""
        try:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Vælg PDF fil", "", "PDF Files (*.pdf)"
            )
            if file_path:
                self.statusBar().showMessage("Behandler PDF...")
                
                # Start PDF processor i en ny tråd
                processor = PDFProcessor(file_path, self.db_path)
                processor.progress.connect(self.update_progress)
                processor.status.connect(self.update_status)
                processor.finished.connect(lambda it=processor: self.on_pdf_processing_finished(it))
                processor.error.connect(self.show_error_message)
                
                # Gem tråden så den ikke bliver garbage collected
                self.threads.append(processor)
                processor.start()
                
                # Tilføj til undo stack
                self.add_to_undo_stack("upload_pdf", file_path)
                
        except Exception as e:
            logging.error(f"Fejl ved PDF upload: {str(e)}")
            QMessageBox.critical(self, "Fejl", 
                f"Der opstod en fejl ved upload af PDF:\n{str(e)}")

    def update_progress(self, value):
        """Opdater progress bar"""
        if hasattr(self, 'progress_bar'):
            self.progress_bar.setValue(value)

    def update_status(self, message):
        """Opdater status besked"""
        self.statusBar().showMessage(message)

    def show_error_message(self, message):
        """Vis fejlbesked"""
        QMessageBox.critical(self, "Fejl", message)

    def on_pdf_processing_finished(self, processor):
        """Håndter færdig PDF processering"""
        self.load_existing_data()
        self.update_status_bar()
        if hasattr(self, 'progress_bar'):
            self.progress_bar.setValue(0)
        
        # Fjern den færdige tråd fra listen
        for thread in self.threads[:]:
            if not thread.isRunning():
                self.threads.remove(thread)

    def upload_multiple(self):
        """
        Denne metode åbner dialogen til at uploade flere filer.
        Brugeren kan tilføje PDF- og billedfiler, se status for hver, og starte upload-processen i en kø.
        Efter upload afsluttes, opdateres dashboardet med de nye data.
        """
        dialog = MultiUploadDialog(self, self.db_path)
        if dialog.exec_() == QDialog.Accepted:
            # Efter at dialogen er lukket med accept,
            # opdater dashboardet med de nye data fra databasen.
            self.load_existing_data()
            self.update_status_bar()


class ImageProcessor(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, image_path, db_path):
        super().__init__()
        self.image_path = image_path
        self.db_path = db_path
        self._is_running = True

    def run(self):
        try:
            self.status.emit("Starter billedanalyse...")
            self.progress.emit(10)

            # Valider billedfil
            if not os.path.exists(self.image_path):
                raise FileNotFoundError(f"Kunne ikke finde billedfilen: {self.image_path}")

            # Tjek filstørrelse
            file_size = os.path.getsize(self.image_path) / (1024 * 1024)  # Convert to MB
            if file_size > 20:
                raise Exception(f"Billedet er for stort ({file_size:.1f} MB). Maksimal størrelse er 20 MB.")

            # Opret OpenAI klient
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                raise Exception("OpenAI API nøgle ikke fundet. Konfigurer venligst API nøglen i indstillinger.")
            
            client = OpenAI(api_key=api_key)
            self.progress.emit(20)
            
            self.status.emit("Analyserer billede med Vision AI...")
            try:
                json_data = extract_products_with_vision(self.image_path, client)
                if not json_data or 'products' not in json_data:
                    raise Exception("Intet brugbart resultat fra Vision AI")
            except Exception as e:
                logging.error(f"Vision API fejl: {str(e)}")
                raise Exception(f"Fejl i billedanalyse: {str(e)}")
                
            self.progress.emit(60)
            
            self.status.emit("Behandler resultater...")
            products = []
            for item in json_data.get('products', []):
                product = {
                    'Article Description Batch': item['product_name'],
                    'Expiry Date': item['expiry_date'],
                    'PDF Source': f"Image: {os.path.basename(self.image_path)}",
                    'ProductID': '',
                    'SKU': '',
                    'EAN Serial No': '',
                    'Remark': '',
                    'Order QTY': '1',
                    'Ship QTY': '1',
                    'UOM': 'EACH'
                }
                products.append(product)
            
            if not products:
                raise Exception("Ingen produkter fundet i billedet")
            
            self.progress.emit(80)
            
            self.status.emit("Gemmer i database...")
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            for product in products:
                cursor.execute('''
                    INSERT INTO products (
                        ProductID, SKU, "Article Description Batch", 
                        "Expiry Date", "EAN Serial No", Remark,
                        "Order QTY", "Ship QTY", UOM, "PDF Source"
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    product['ProductID'],
                    product['SKU'],
                    product['Article Description Batch'],
                    product['Expiry Date'],
                    product['EAN Serial No'],
                    product['Remark'],
                    product['Order QTY'],
                    product['Ship QTY'],
                    product['UOM'],
                    product['PDF Source']
                ))
            
            conn.commit()
            conn.close()
            
            self.progress.emit(100)
            self.status.emit(f"Færdig! Tilføjet {len(products)} produkter")
            self.finished.emit()
            
        except Exception as e:
            logging.error(f"Fejl ved behandling af billede: {str(e)}")
            self.error.emit(str(e))


def exception_hook(exctype, value, traceback):
    logging.error("Uncaught exception", exc_info=(exctype, value, traceback))
    QMessageBox.critical(None, "Uventet fejl",
                         f"Der opstod en uventet fejl: {value}\n\n"
                         f"En logfil er blevet gemt i {get_app_data_dir()}\n"
                         f"Venligst send denne logfil til support for hjælp.")
    sys._excepthook(exctype, value, traceback)
    sys.exit(1)


def extract_products_with_gpt(text_content, client):
    """Udtrækker produktinformation ved hjælp af GPT"""
    try:
        logging.info("Starter GPT analyse af tekst")
        
        # Rens teksten for potentielle problematiske tegn
        cleaned_text = text_content.replace('"', "'").replace('\n', ' ').strip()
        
        # Log den rensede tekst der sendes til AI
        print("\n=== TEKST SENDT TIL AI ===")
        print(cleaned_text)
        print("=== SLUT PÅ INPUT TEKST ===\n")
        
        system_prompt = """
        Du er en specialiseret AI til at analysere leveringssedler fra Sweetspot A/S.
        Din opgave er at udtrække information KUN om produkter med udløbsdato og returnere det som JSON data.
        
        VIGTIGE INSTRUKTIONER:
        1. MEGET VIGTIGT - Inkluder KUN produkter der har en udløbsdato
           - Ignorer produkter som bægre, handsker og andet udstyr
           - Fokuser kun på fødevarer og andre produkter med udløbsdato
        
        2. Hver relevant produktlinje skal indeholde:
           - SKU (præcis 5 cifre, f.eks. '16404', '12228')
           - Article Description Batch (produktnavn og batch, f.eks. 'Ritter Sport Mælk', 'Twix Single 32x50g')
           - ProductID (1-3 cifre, f.eks. '98', '64')
           - EAN Serial No (13-14 cifre eller tomt hvis ingen stregkode)
           - Order QTY (antal bestilt)
           - Expiry Date (DD.MM.YYYY format, f.eks. '19.12.2024')
           - Ship QTY (antal leveret)
           - UOM (altid "EACH")

        3. Valideringsregler:
           - SKU SKAL være præcis 5 cifre
           - Article Description Batch SKAL udfyldes
           - ProductID SKAL være 1-3 cifre
           - EAN Serial No kan være enten 13-14 cifre eller tomt
           - Expiry Date SKAL være i DD.MM.YYYY format
           - Ignorer headers, fodnoter og ikke-relevante produkter

        VIGTIGT: Returner data i præcis dette format og brug PRÆCIS disse feltnavne:
        {
            "products": [
                {
                    "SKU": "16404",
                    "Article Description Batch": "Ritter Sport Mælk",
                    "ProductID": "98",
                    "EAN Serial No": "4000417222602",
                    "Order QTY": "1",
                    "Expiry Date": "19.12.2024",
                    "Ship QTY": "1",
                    "UOM": "EACH"
                }
            ]
        }
        """

        logging.info("Sender forespørgsel til GPT")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": f"Analyser følgende leveringsseddel og returner KUN produkter med udløbsdato som JSON: {cleaned_text}"
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=4000,
            temperature=0.3
        )
        
        logging.info("GPT analyse fuldført, parser response")
        content = response.choices[0].message.content
        
        # Log AI's response
        print("\n=== AI RESPONSE ===")
        print(content)
        print("=== SLUT PÅ AI RESPONSE ===\n")
        
        try:
            result = json.loads(content)
            if not isinstance(result, dict) or 'products' not in result:
                logging.error("Ugyldigt response format - mangler 'products' key")
                return {"products": []}
            
            raw_products = result.get('products', [])
            logging.info(f"Fundet {len(raw_products)} produkter før validering")
            
            validated_products = []
            for product in raw_products:
                # Log det originale produkt
                logging.debug(f"Validerer produkt: {product}")
                
                # Normaliser feltnavne
                if 'ArticleDescriptionBatch' in product:
                    product['Article Description Batch'] = product.pop('ArticleDescriptionBatch')
                if 'EANSerialNo' in product:
                    product['EAN Serial No'] = product.pop('EANSerialNo')
                if 'ExpiryDate' in product:
                    product['Expiry Date'] = product.pop('ExpiryDate')
                if 'OrderQTY' in product:
                    product['Order QTY'] = product.pop('OrderQTY')
                if 'ShipQTY' in product:
                    product['Ship QTY'] = product.pop('ShipQTY')

                # Valider felter
                validation_errors = []
                
                # SKU validering
                sku = str(product.get('SKU', ''))
                if not (len(sku) == 5 and sku.isdigit()):
                    validation_errors.append(f"SKU: {sku} (skal være 5 cifre)")

                # ProductID validering
                product_id = str(product.get('ProductID', ''))
                if not re.match(r'^\d{1,3}$', product_id):
                    validation_errors.append(f"ProductID: {product_id} (skal være 1-3 cifre)")

                # EAN validering
                ean = str(product.get('EAN Serial No', ''))
                if ean and not re.match(r'^\d{13,14}$', ean):
                    validation_errors.append(f"EAN: {ean} (skal være tomt eller 13-14 cifre)")

                # Expiry Date validering
                expiry_date = str(product.get('Expiry Date', ''))
                if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', expiry_date):
                    validation_errors.append(f"Expiry Date: {expiry_date} (skal være DD.MM.YYYY)")

                # Article Description Batch validering
                if not product.get('Article Description Batch'):
                    validation_errors.append("Manglende Article Description Batch")

                if validation_errors:
                    logging.warning(f"Produkt validering fejlede:\n" + "\n".join(validation_errors))
                    continue
                
                # Hvis EAN er tomt, sæt det til en tom streng
                if not ean:
                    product['EAN Serial No'] = ''
                
                validated_products.append(product)
                logging.debug(f"Produkt valideret og godkendt: {product}")

            logging.info(f"Validering færdig. {len(validated_products)} af {len(raw_products)} produkter godkendt")
            return {"products": validated_products}
            
        except json.JSONDecodeError as e:
            logging.error(f"JSON parsing fejl: {str(e)}")
            logging.error(f"Problematisk JSON: {content}")
            raise Exception(f"Fejl ved parsing af AI response: {str(e)}")
            
    except Exception as e:
        logging.error(f"GPT API fejl: {str(e)}")
        raise Exception(f"GPT Fejl: {str(e)}")


def process_pdf(pdf_path):
    client = OpenAI()  # Initialiser OpenAI client
    
    with open(pdf_path, 'rb') as file:
        pdf_reader = PyPDF2.PdfReader(file)
        all_text = ""
        for page in pdf_reader.pages:
            all_text += page.extract_text()
            
    # Brug GPT til at udtrække produkter
    result = extract_products_with_gpt(all_text, client)
    return result['products']


def extract_products_with_vision(image_path, client):
    """Udtrækker produktinformation fra billede ved hjælp af GPT-4 Vision"""
    try:
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            
        response = client.chat.completions.create(
            model="gpt-4o",  # Opdateret model navn
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """Analyser dette billede af en udløbsdatoliste og returner et JSON objekt med følgende struktur:
                            {
                                "products": [
                                    {
                                        "product_name": "Produktnavn",
                                        "expiry_date": "DD.MM.YYYY"
                                    }
                                ]
                            }
                            
                            VIGTIGT:
                            - Find overskriften med måneden og året
                            - For hver linje, udtræk produktnavn og dato
                            - Hvis kun dagen er angivet i listen, brug måneden og året fra overskriften
                            - Konverter alle datoer til formatet DD.MM.YYYY
                            - Bevar præcis produktnavne som de står i billedet
                            - Returner KUN JSON, ingen ekstra tekst"""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            max_tokens=1500,
            temperature=0.2  # Lavere temperatur for mere præcise resultater
        )
        
        # Hent response content og log det
        content = response.choices[0].message.content.strip()
        logging.info(f"Raw API response: {content}")
        
        # Find JSON i responset
        try:
            # Først prøv at parse hele responset som JSON
            result = json.loads(content)
        except json.JSONDecodeError:
            # Hvis det fejler, prøv at finde JSON i teksten
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if not json_match:
                raise ValueError("Intet JSON fundet i API response")
            result = json.loads(json_match.group(0))
        
        # Valider JSON struktur
        if not isinstance(result, dict) or 'products' not in result:
            raise ValueError("Ugyldigt JSON format - mangler 'products' array")
        
        # Valider og formater datoer
        for product in result['products']:
            if 'expiry_date' not in product:
                raise ValueError(f"Manglende udløbsdato for produkt: {product.get('product_name', 'Ukendt')}")
            
            # Sikr at datoen er i korrekt format
            try:
                date_parts = product['expiry_date'].split('.')
                if len(date_parts) == 3:
                    day, month, year = date_parts
                    # Valider dag og måned
                    if not (1 <= int(day) <= 31 and 1 <= int(month) <= 12):
                        raise ValueError
                else:
                    raise ValueError
            except:
                raise ValueError(f"Ugyldig dato format for produkt: {product.get('product_name', 'Ukendt')}")
        
        logging.info(f"Fandt {len(result['products'])} produkter i billedet")
        return result
            
    except Exception as e:
        logging.error(f"Fejl i Vision API kald: {str(e)}")
        raise


class APIKeyDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OpenAI API Nøgle")
        self.setModal(True)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Forklarende tekst
        info_label = QLabel(
            "Indtast din OpenAI API nøgle. Nøglen vil blive gemt sikkert i dine lokale indstillinger."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Input felt til API nøgle
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("sk-...")
        self.api_key_input.setEchoMode(QLineEdit.Password)  # Skjul nøglen
        layout.addWidget(self.api_key_input)
        
        # Knapper
        button_layout = QHBoxLayout()
        save_button = QPushButton("Gem")
        save_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Annuller")
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)

    def get_api_key(self):
        return self.api_key_input.text().strip()


class UploadItemWidget(QWidget):
    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.file_path = file_path  # Gemmer filstien for dette upload-item
        self.processor = None  # Her lagres henvisningen til QThread (PDFProcessor/ImageProcessor)
        self.init_ui()

    def init_ui(self):
        # Opret et vandret layout
        self.layout = QHBoxLayout(self)
        # Vis filnavnet (kun basename)
        self.file_label = QLabel(os.path.basename(self.file_path))
        self.layout.addWidget(self.file_label)
        # Fjern knap for at tillade brugeren at fjerne filen
        self.remove_button = QPushButton("Fjern")
        self.layout.addWidget(self.remove_button)
        # Progress bar som viser upload-progresjon, gemmes indtil processtart
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedWidth(100)
        self.progress_bar.hide()  # Skjul indtil upload begynder
        self.layout.addWidget(self.progress_bar)
        # Statuslabel der fortæller hvilken status filen er i (venter, upload, færdig, fejl osv.)
        self.status_label = QLabel("Venter")
        self.layout.addWidget(self.status_label)
        self.setLayout(self.layout)

    def update_progress(self, value):
        # Opdaterer progress bar med den modtagne værdi
        self.progress_bar.setValue(value)

    def update_status(self, message):
        # Opdater status label med den modtagne besked
        self.status_label.setText(message)


class MultiUploadDialog(QDialog):
    def __init__(self, parent=None, db_path=None):
        super().__init__(parent)
        self.db_path = db_path  # Database stien, så de samme upload-funktioner kan anvendes
        self.setWindowTitle("Upload Flere Filer")
        self.setModal(True)
        self.resize(600, 400)
        self.upload_items = []  # Liste til at lagre UploadItemWidget objekter
        self.current_upload_index = 0
        self.upload_error_occurred = False  # Flag der indikerer fejl
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        # Tilføj "Tilføj Filer" knap
        self.add_files_button = QPushButton("Tilføj Filer")
        self.add_files_button.setToolTip("Tilføj PDF- eller billedfiler")
        self.add_files_button.clicked.connect(self.add_files)
        layout.addWidget(self.add_files_button)

        # Opret et scroll-område til at vise listen af filer
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.file_list_widget = QWidget()
        self.file_list_layout = QVBoxLayout(self.file_list_widget)
        self.file_list_widget.setLayout(self.file_list_layout)
        self.scroll_area.setWidget(self.file_list_widget)
        layout.addWidget(self.scroll_area)

        # Knapper til at starte upload eller annullere processen
        button_layout = QHBoxLayout()
        self.upload_button = QPushButton("Upload")
        self.upload_button.setToolTip("Start upload af filerne i køen")
        self.upload_button.clicked.connect(self.start_upload)
        button_layout.addWidget(self.upload_button)
        self.cancel_button = QPushButton("Annuller")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
        self.setLayout(layout)

    def add_files(self):
        # Åbn en dialog der tillader valg af eksisterende filer (PDF eller billeder)
        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.ExistingFiles)
        file_dialog.setNameFilter("PDF Filer (*.pdf);;Image Filer (*.png *.jpg *.jpeg)")
        if file_dialog.exec_():
            files = file_dialog.selectedFiles()
            for file_path in files:
                # Opret et upload-item widget for hver fil valgt
                item = UploadItemWidget(file_path)
                # Tilknyt fjern-knappen, så den fjerner item fra listen i dialogen
                item.remove_button.clicked.connect(lambda checked, item=item: self.remove_item(item))
                self.upload_items.append(item)
                self.file_list_layout.addWidget(item)

    def remove_item(self, item):
        # Fjern upload-item widget hvis brugeren trykker "Fjern"
        if item in self.upload_items:
            self.upload_items.remove(item)
            item.setParent(None)
            item.deleteLater()

    def start_upload(self):
        if not self.upload_items:
            QMessageBox.warning(self, "Ingen filer", "Der er ingen filer at uploade.")
            return

        # Deaktiver muligheden for at tilføje flere filer og starte upload igen
        self.add_files_button.setEnabled(False)
        self.upload_button.setEnabled(False)
        self.current_upload_index = 0
        self.upload_error_occurred = False
        # Start processen med at uploade den første fil i køen
        self.process_next_file()

    def process_next_file(self):
        # Hvis vi er færdige med alle filer, vis en besked og luk dialogen positivt
        if self.current_upload_index >= len(self.upload_items):
            QMessageBox.information(self, "Upload færdig", "Alle filer er blevet uploaded.")
            self.accept()
            return

        # Hent det nuværende upload-item
        item = self.upload_items[self.current_upload_index]
        file_path = item.file_path

        # Bestem filtype og opret den relevante processor (PDFProcessor eller ImageProcessor)
        if file_path.lower().endswith(".pdf"):
            # PDF-fil: brug den eksisterende PDFProcessor
            processor = PDFProcessor(file_path, self.db_path)
        elif any(file_path.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg"]):
            # Billedfil: brug den eksisterende ImageProcessor
            processor = ImageProcessor(file_path, self.db_path)
        else:
            # Hvis filtypen ikke understøttes, opdater status og spring over filen
            item.update_status("Ikke understøttet filtype")
            self.current_upload_index += 1
            QTimer.singleShot(1000, self.process_next_file)
            return

        # Vis progress bar for filen
        item.progress_bar.show()
        # Tilknyt processorens signaler til item
        processor.progress.connect(lambda value, it=item: it.update_progress(value))
        processor.status.connect(lambda msg, it=item: it.update_status(msg))
        processor.error.connect(lambda err, it=item: self.handle_processor_error(err, it))
        # Når processor er færdig, fortsæt med næste fil
        processor.finished.connect(lambda it=item: self.on_processor_finished(it))
        # Start processor-tråden
        processor.start()
        # Gem processor-referencen i item for at forhindre, at den bliver garbage collected
        item.processor = processor

    def handle_processor_error(self, error, item):
        # Hvis der opstår en fejl under upload, vis fejlbesked og stop processen
        item.update_status(f"Fejl: {error}")
        self.upload_error_occurred = True
        QMessageBox.critical(self, "Upload Fejl",
                             f"Fejl ved upload af fil {os.path.basename(item.file_path)}: {error}")
        self.reject()

    def on_processor_finished(self, item):
        # Hvis en fejl opstod, skal ingen yderligere filer processeres
        if self.upload_error_occurred:
            return
        # Marker filen som færdig med upload
        item.update_status("Upload færdig")
        item.progress_bar.setValue(100)
        # Gå videre til næste fil efter en kort forsinkelse
        self.current_upload_index += 1
        QTimer.singleShot(500, self.process_next_file)


if __name__ == "__main__":
    setup_logging()
    logging.info("Program startet")

    sys._excepthook = sys.excepthook
    sys.excepthook = exception_hook

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(resource_path('sweetspot_logo.ico')))
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

