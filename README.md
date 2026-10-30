# ai-pointer-for-windows

Clone open-source del **Magic Pointer** di Googlebook OS, realizzato per Windows con Python + Groq (Qwen 27B vision).

## Cosa fa

Scuotendo il mouse (shake gesture) si attiva un selettore circolare stile **Circle to Search**. Si trascina per cerchiare un'area dello schermo, si rilascia e si apre una finestra chat con:

* l'anteprima dell'immagine selezionata
* fino a 3 suggerimenti automatici generati da Groq (Qwen 3.8 27B)
* un campo per scrivere un prompt personalizzato sull'immagine
* copia negli appunti con un clic sui suggerimenti

## Requisiti

* Python 3.10+
* Una chiave API [Groq](https://console.groq.com/) (gratuita)

## Installazione

```powershell
git clone https://github.com/vin10122/ai-pointer-for-windows.git
cd ai-pointer-for-windows
pip install -r requirements.txt
```

Crea un file `.env` nella cartella del progetto con la tua chiave Groq:

```
GROQ_API_KEY=la_tua_chiave_qui
GROQ_MODEL=qwen/qwen3.8-27b
```

## Avvio

```powershell
python magic_pointer.py
```

*Scuoti il mouse* per attivare il selettore circolare. Trascina per ingrandire il cerchio, rilascia per confermare (Esc per annullare).

## File

| File | Descrizione |
|------|-------------|
| `magic_pointer.py` | Logica principale: rilevazione shake, selettore circolare, chat Groq |
| `drawer_webview.py` | Componente webview drawer (integrazione UI) |
| `requirements.txt` | Dipendenze Python |
| `.env` | Chiavi API (non committato, crealo tu) |
| `.gitignore` | File esclusi da git |

## Licenza

MIT
