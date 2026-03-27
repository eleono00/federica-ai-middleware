import os
import json
import hashlib
from openai import OpenAI
from dotenv import load_dotenv

# --- CONFIGURAZIONE ---
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    print(" ERRORE: Manca OPENAI_API_KEY nel file .env")
    exit()

# Inizializzazione client OpenAI (Sintassi Ufficiale Stabile)
CLIENT = OpenAI(api_key=api_key)

CARTELLA_SORGENTE = "materiale_per_openai"
FILE_STATO = "stato_vettoriale.json"
FILE_CONFIG = "config_ids.json"

def calcola_hash(path):
    """Genera un'impronta digitale unica per il contenuto del file"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""): 
            h.update(chunk)
    return h.hexdigest()

def get_vector_store():
    """Recupera o crea il Vector Store su OpenAI"""
    vs_id = None
    if os.path.exists(FILE_CONFIG):
        with open(FILE_CONFIG, 'r') as f:
            try: 
                vs_id = json.load(f).get("vector_store_id")
            except: 
                pass
    
    if vs_id:
        try: 
            vs = CLIENT.vector_stores.retrieve(vs_id)
            print(f" Collegato al Vector Store: {vs.name}")
            return vs
        except: 
            print(" Vector Store non trovato. Ne creo uno nuovo.")

    vs = CLIENT.vector_stores.create(name="Archivio Guide Moodle -TEST")
    with open(FILE_CONFIG, 'w') as f: 
        json.dump({"vector_store_id": vs.id}, f)
    print(f" Nuovo Vector Store creato: {vs.id}")
    return vs

def main():
    print("\n AVVIO SINCRONIZZAZIONE (Supporto Multi-Formato)...")
    
    # Verifica esistenza cartella scaricata da Drive
    if not os.path.exists(CARTELLA_SORGENTE):
        print(f" Errore: Cartella '{CARTELLA_SORGENTE}' non trovata. Esegui scarica_da_drive.py")
        return

    vector_store = get_vector_store()
    
    # Carica la memoria dello stato vettoriale
    stato = {}
    if os.path.exists(FILE_STATO):
        with open(FILE_STATO, 'r') as f: 
            stato = json.load(f)

    # --- AGGIORNAMENTO REGOLE ---
    # Accettiamo solo testo e presentazioni (come da nuovo script Drive)
    estensioni_valide = ('.pdf', '.docx', '.doc', '.pptx', '.txt', '.xlsx', '.csv')
    files_locali = [f for f in os.listdir(CARTELLA_SORGENTE) if f.lower().endswith(estensioni_valide)]
    
    print(f" Analisi di {len(files_locali)} file in corso...")

    # 1. GESTIONE UPLOAD E MODIFICHE
    for nome in files_locali:
        path = os.path.join(CARTELLA_SORGENTE, nome)
        current_hash = calcola_hash(path)
        
        # Recupera dati storici del file
        vecchio_dato = stato.get(nome, {})
        vecchio_id = vecchio_dato.get("openai_id")
        vecchio_hash = vecchio_dato.get("hash")
        
        # Se il file è invariato, lo saltiamo
        if vecchio_id and current_hash == vecchio_hash:
            print(f"   ok: {nome}")
            continue

        # Gestione file modificati
        if vecchio_id:
            print(f"    Modifica rilevata: {nome}. Sostituzione...")
            try: 
                # Rimuove prima dal Vector Store, poi dai file generali
                CLIENT.vector_stores.files.delete(vector_store_id=vector_store.id, file_id=vecchio_id)
                CLIENT.files.delete(vecchio_id)
            except: 
                pass

        print(f"    Caricamento: {nome}...")
        try:
            with open(path, "rb") as f:
                f_ai = CLIENT.files.create(file=f, purpose='assistants')
            
            CLIENT.vector_stores.files.create(
                vector_store_id=vector_store.id, 
                file_id=f_ai.id
            )
            
            stato[nome] = {"openai_id": f_ai.id, "hash": current_hash}
        except Exception as e:
            print(f"       Errore upload {nome}: {e}")

    # 2. GESTIONE FILE RIMOSSI (Mirroring)
    nomi_su_drive = set(files_locali)
    da_rimuovere = [f for f in stato if f not in nomi_su_drive]
    for f_da_eliminare in da_rimuovere:
        print(f"     Rimosso in locale, elimino da OpenAI: {f_da_eliminare}")
        try:
            vecchio_id = stato[f_da_eliminare]['openai_id']
            CLIENT.vector_stores.files.delete(vector_store_id=vector_store.id, file_id=vecchio_id)
            CLIENT.files.delete(vecchio_id)
        except:
            pass
        del stato[f_da_eliminare]

    # Salva lo stato aggiornato
    with open(FILE_STATO, 'w') as f: 
        json.dump(stato, f, indent=4)
    
    print("\n Sincronizzazione OpenAI completata.")

if __name__ == "__main__":
    main()
