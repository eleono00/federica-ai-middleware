# 🤖 Middleware AI: Sincronizzazione Drive-OpenAI (Hybrid RAG)

Questo repository contiene il codice sorgente (Middleware Python) sviluppato per alimentare la *Knowledge Base* dell'AI Tutor del centro Federica Web Learning (Università degli Studi di Napoli Federico II).

Il sistema funge da ponte logistico tra un archivio documentale su **Google Drive** e la memoria semantica (Vector Store) di **OpenAI**, automatizzando l'estrazione, la conversione e l'aggiornamento dei documenti istituzionali per il supporto Moodle.

## ⚙️ Architettura del Sistema

Il middleware è composto da due script indipendenti che operano in sequenza:

1. **`scarica_da_drive.py` (L'Estrattore)**
   * Si connette in modo sicuro a Google Drive tramite Service Account (GCP).
   * Naviga ricorsivamente nelle cartelle autorizzate.
   * Scarica solo i file nuovi o modificati di recente.
   * Converte i documenti Google nei formati fisici supportati dall'AI (es. `.txt`, `.pdf`).
   * Genera un catalogo aggiornato dei link per permettere all'AI di citare le fonti.

2. **`sync_core.py` (Il Sincronizzatore)**
   * Calcola l'Hash MD5 dei file locali per rilevare variazioni nel testo.
   * Gestisce le *Assistants API* di OpenAI caricando solo i documenti aggiornati.
   * Elimina le vecchie versioni dei file dal Vector Store per evitare ridondanze.
   * Esegue un mirroring: rimuove da OpenAI i file che non esistono più su Drive.

## 🚀 Prerequisiti e Installazione

Il progetto è progettato per girare all'interno di un Virtual Environment Python isolato.

```bash
# Creazione ambiente virtuale
python3 -m venv venv
source venv/bin/activate

# Installazione dipendenze
pip install google-api-python-client google-auth-oauthlib openai python-dotenv tqdm
