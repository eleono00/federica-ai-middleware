import os
import io
import json
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from tqdm import tqdm

# --- CONFIGURAZIONE ---
load_dotenv()
SERVICE_ACCOUNT_FILE = os.getenv('GOOGLE_CREDENTIALS')
ROOT_FOLDER_ID = os.getenv('DRIVE_FOLDER_ID')
OUTPUT_DIR = 'materiale_per_openai'
STATO_DRIVE_FILE = 'stato_drive.json'
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

if not ROOT_FOLDER_ID:
    raise ValueError("ERRORE: Manca DRIVE_FOLDER_ID nel file .env")

def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

def scarica_fisicamente(service, item, path_destinazione):
    file_id = item['id']
    mime = item['mimeType']
    nome = item['name']
    link_drive = item.get('webViewLink', '')
    request = None
    
    # --- REGOLE DI ESPORTAZIONE E DOWNLOAD ---
    if mime == 'application/vnd.google-apps.document':
        # I Google Docs diventano .txt
        request = service.files().export_media(fileId=file_id, mimeType='text/plain')
    elif mime == 'application/vnd.google-apps.presentation':
        # Le Google Slides diventano .pdf
        request = service.files().export_media(fileId=file_id, mimeType='application/pdf')
    elif mime in ['application/pdf', 'application/vnd.openxmlformats-officedocument.presentationml.presentation']:
        # I PDF e i file .pptx di Microsoft vengono scaricati così come sono
        request = service.files().get_media(fileId=file_id)
    else:
        return False

    if request:
        with io.FileIO(path_destinazione, 'wb') as fh:
            try:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                with tqdm(total=100, unit='%', leave=False, desc=f"Download {nome[:15]}...") as pbar:
                    while done is False:
                        status, done = downloader.next_chunk()
                        if status: pbar.update(int(status.progress() * 100) - pbar.n)
            except Exception as e:
                print(f"    Errore download {nome}: {e}")
                fh.close()
                if os.path.exists(path_destinazione): os.remove(path_destinazione)
                return False
        
        # --- INIEZIONE DEL LINK SOLO PER I FILE DI TESTO (.txt) ---
        if path_destinazione.endswith('.txt') and link_drive:
            with open(path_destinazione, 'a', encoding='utf-8') as f:
                f.write("\n\n" + "="*50 + "\n")
                f.write(f"LINK ORIGINALE GOOGLE DRIVE: {link_drive}\n")
                f.write("="*50 + "\n")
                
        return True
    return False

def processa_cartella_ricorsiva(service, folder_id, file_validi_list, stato_drive):
    query = f"'{folder_id}' in parents and trashed = false"
    
    results = service.files().list(
        q=query, supportsAllDrives=True, includeItemsFromAllDrives=True,
        fields="files(id, name, mimeType, webViewLink, modifiedTime)", pageSize=1000
    ).execute()
    
    items = results.get('files', [])

    for item in items:
        nome = item['name']
        mime = item['mimeType']
        data_modifica_drive = item.get('modifiedTime')
        
        if mime == 'application/vnd.google-apps.folder':
            print(f" Entro in: {nome}")
            processa_cartella_ricorsiva(service, item['id'], file_validi_list, stato_drive)
            continue
            
        # Filtro Rigido: Docs, Slides, PDF e PPTX
        tipi_ammessi = [
            'application/vnd.google-apps.document', 
            'application/vnd.google-apps.presentation',
            'application/pdf',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation' # Supporto PPTX
        ]
        
        if mime not in tipi_ammessi:
            continue

        # Gestione Estensioni
        ext = ""
        if mime == 'application/vnd.google-apps.document': ext = '.txt'
        elif mime == 'application/vnd.google-apps.presentation': ext = '.pdf'
        elif mime == 'application/vnd.openxmlformats-officedocument.presentationml.presentation': ext = '.pptx'
        
        if nome.lower().endswith(ext) or (ext == "" and "." in nome): 
            nome_finale = nome
        else: 
            nome_finale = nome + ext
            
        # Sicurezza per i file nativi che potrebbero non avere estensione nel nome
        if mime == 'application/pdf' and not nome_finale.lower().endswith('.pdf'):
            nome_finale += '.pdf'
        elif mime == 'application/vnd.openxmlformats-officedocument.presentationml.presentation' and not nome_finale.lower().endswith('.pptx'):
            nome_finale += '.pptx'
        
        path_completo = os.path.join(OUTPUT_DIR, nome_finale)
        file_validi_list.append(nome_finale)

        # Controllo se invariato
        if nome_finale in stato_drive and stato_drive[nome_finale] == data_modifica_drive:
            if os.path.exists(path_completo):
                print(f"    OK (Invariato su Drive): {nome_finale}")
                continue

        print(f"     Download/Aggiornamento: {nome_finale}")
        if scarica_fisicamente(service, item, path_completo):
            stato_drive[nome_finale] = data_modifica_drive

def main():
    if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)
    print(f" Connessione a Drive (Root ID: {ROOT_FOLDER_ID})...")
    service = get_drive_service()
    
    stato_drive = {}
    if os.path.exists(STATO_DRIVE_FILE):
        with open(STATO_DRIVE_FILE, 'r', encoding='utf-8') as f:
            try: stato_drive = json.load(f)
            except: pass

    file_validi_list = []
    
    print(" Inizio sincronizzazione Smart da Drive...")
    processa_cartella_ricorsiva(service, ROOT_FOLDER_ID, file_validi_list, stato_drive)
    
    # Pulizia
    file_locali = os.listdir(OUTPUT_DIR)
    for f_local in file_locali:
        if f_local not in file_validi_list:
            print(f" Pulizia: Rimuovo file obsoleto -> {f_local}")
            try: os.remove(os.path.join(OUTPUT_DIR, f_local))
            except: pass
            if f_local in stato_drive: del stato_drive[f_local]

    with open(STATO_DRIVE_FILE, 'w', encoding='utf-8') as f:
        json.dump(stato_drive, f, indent=4, ensure_ascii=False)

    print(f"\n Finito! Totale file monitorati: {len(file_validi_list)}")

if __name__ == '__main__':
    main()
