"""Small shared Italian/English catalog and persistent desktop preference."""
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


EN = {
    'Lingua': 'Language',
    'Copia immagine': 'Copy image',
    'Apri immagine per copiare testo': 'Open image to copy text',
    'Cerca con Google Lens': 'Search with Google Lens',
    'Domanda facoltativa, per esempio: dove posso comprarlo?': 'Optional question, for example: where can I buy it?',
    'Si apre la finestra Lens: completa lì eventuali richieste di consenso. L’AI interpreta i risultati nella chat. Il ritaglio va a Google e i risultati all’API configurata.': 'The Lens window opens: complete any consent requests there. AI explains the results in chat. The capture goes to Google and the results to your configured API.',
    'Usa Lens per le prossime domande': 'Use Lens for follow-up questions',
    'Invia a Lens': 'Send to Lens',
    'Cerca questa immagine con Lens': 'Search this image with Lens',
    'Ricerca su Google Lens…': 'Searching Google Lens…',
    'Attendo Google Lens…': 'Waiting for Google Lens…',
    'Risposta AI basata sui risultati Lens': 'AI answer based on Lens results',
    'Richiesta Lens interrotta.': 'Lens request interrupted.',
    'Lens non ha completato la richiesta. Puoi riprovare; dettagli in %TEMP%\\shakesearch.log.': 'Lens did not complete the request. Try again; details in %TEMP%\\shakesearch.log.',
    'Copia in corso…': 'Copying…',
    'Immagine copiata negli appunti.': 'Image copied to clipboard.',
    'Impossibile copiare l’immagine. Riprova.': 'Unable to copy the image. Try again.',
    'Impossibile aprire l’immagine. Riprova.': 'Unable to open the image. Try again.',
    'Impossibile inviare la domanda. Riprova.': 'Unable to send the question. Try again.',
    'Schermo intero (F11)': 'Fullscreen (F11)',
    'Chiudi (Esc)': 'Close (Esc)',
    'Selezione': 'Selection',
    '⛶ Schermo intero': '⛶ Fullscreen',
    '🗗 Finestra': '🗗 Window',
    '⏳ Analisi della selezione…': '⏳ Analyzing selection...',
    '✨ Suggerimenti correlati': '✨ Related suggestions',
    'Chiedi qualcosa o cerchia…': 'Ask anything or circle...',
    'Immagine non disponibile. Esegui una nuova cattura.': 'Image unavailable. Capture a new selection.',
    'La chat è stata chiusa.': 'The chat has been closed.',
    'Impossibile copiare l’immagine. Riprova; dettagli in shakesearch.log.': 'Unable to copy the image. Try again; details in shakesearch.log.',
    'Aggiorna le dipendenze: python -m pip install -r requirements.txt': 'Update dependencies: python -m pip install -r requirements.txt',
    'Risultati Lens ricevuti. L’AI sta preparando la risposta…': 'Lens results received. AI is preparing the answer…',
    'Risposta Lens pronta.': 'Lens answer ready.',
    'Richiesta Lens annullata o sconosciuta.': 'Lens request cancelled or unknown.',
    'Richiesta Lens annullata.': 'Lens request cancelled.',
    'Risultati originali Lens.': 'Original Lens results.',
    'L’API non ha risposto in tempo. Mostro il testo originale di Lens.': 'The API did not respond in time. Showing the original Lens text.',
    'Configura GROQ_API_KEY per usare le spiegazioni AI.': 'Configure GROQ_API_KEY to use AI explanations.',
    'Impossibile aprire l’immagine. Controlla shakesearch.log.': 'Unable to open the image. Check shakesearch.log.',
    'Configura GROQ_API_KEY per interpretare i risultati. Mostro il testo originale di Lens.': 'Configure GROQ_API_KEY to interpret results. Showing the original Lens text.',
    'Lens non ha restituito testo da interpretare.': 'Lens returned no text to interpret.',
    'Interpretazione AI non disponibile. Mostro i risultati originali di Lens.': 'AI interpretation unavailable. Showing the original Lens results.',
    'Scrivi una domanda di massimo 500 caratteri.': 'Write a question of up to 500 characters.',
    'La sessione Lens non è più disponibile. Riprova.': 'The Lens session is no longer available. Try again.',
    'Attendi le risposte Lens già in corso prima di inviare altre domande.': 'Wait for pending Lens answers before sending more questions.',
    'Richiesta Lens in coda…': 'Lens request queued…',
    'Il processo Lens si è chiuso. La chat è ancora disponibile: puoi riprovare.': 'The Lens process closed. The chat is still available: you can try again.',
    'Impossibile avviare Lens. Controlla shakesearch.log e riprova.': 'Unable to start Lens. Check shakesearch.log and try again.',
    'Lens non ha risposto entro il tempo previsto. Il processo è stato fermato; puoi riprovare.': 'Lens did not respond in time. Its process was stopped; you can try again.',
    'Risultati Lens letti. Puoi fare un’altra domanda.': 'Lens results read. You can ask another question.',
    'Ricerca Lens non completata.': 'Lens search not completed.',
    'Richiesta Lens sconosciuta.': 'Unknown Lens request.',
    'Il processo Lens si è arrestato.': 'The Lens process stopped.',
    'La sessione Lens non contiene ancora una ricerca valida.': 'The Lens session does not yet contain a valid search.',
    'Consenso acquisito. Invio l’immagine dalla stessa sessione Google…': 'Consent received. Sending the image from the same Google session…',
    'Non sono riuscito a leggere risultati reali da Lens. Google potrebbe richiedere una verifica o aver cambiato la pagina.': 'Unable to read actual Lens results. Google may require verification or may have changed the page.',
    'La finestra Lens può aprire soltanto pagine Google autorizzate.': 'The Lens window can only open allowed Google pages.',
    'La sessione Lens è stata chiusa.': 'The Lens session has been closed.',
    'Non sono riuscito a inviare automaticamente il file dalla sessione Google autorizzata.': 'Unable to automatically send the file from the authorized Google session.',
    'La finestra Google è stata chiusa prima di completare la ricerca. Puoi riprovare.': 'The Google window was closed before the search completed. You can try again.',
    'Google non ha fornito risultati leggibili. Controlla la pagina nella finestra Lens aperta, completa eventuali verifiche e riprova.': 'Google did not provide readable results. Check the open Lens window, complete any verification and try again.',
    'Completa il consenso nella finestra Google. Riprenderò automaticamente da quella stessa sessione.': 'Complete consent in the Google window. I will resume automatically in that same session.',
    'Lens non ha ancora fornito risultati leggibili. Mostro la stessa finestra Google e continuo ad attendere la risposta.': 'Lens has not provided readable results yet. Showing the same Google window and continuing to wait.',
    'Apro Google Lens. Completa eventuali richieste nella finestra Google…': 'Opening Google Lens. Complete any requests in the Google window…',
    'Invio diretto dell’immagine a Google Lens…': 'Sending the image directly to Google Lens…',
    'La finestra interna non riesce a raggiungere Google Lens. Controlla la connessione e riprova.': 'The internal window cannot reach Google Lens. Check your connection and try again.',
    'Lens ha aperto una pagina esterna inattesa; non la leggerò come risultato.': 'Lens opened an unexpected external page; it will not be read as a result.',
    'Consenso completato. Attendo i risultati di Lens…': 'Consent completed. Waiting for Lens results…',
    'Google Lens ha restituito una pagina di errore, non risultati.': 'Google Lens returned an error page instead of results.',
    'Google Lens non ha confermato una ricerca associata all’immagine.': 'Google Lens did not confirm a search associated with the image.',
    'Google Lens ha restituito il modulo di caricamento invece dei risultati. L’immagine non è stata associata a una ricerca leggibile.': 'Google Lens returned the upload form instead of results. The image was not associated with a readable search.',
    'Lens non ha mantenuto il riferimento all’immagine dopo il consenso.': 'Lens did not retain the image reference after consent.',
    'Lens è già attivo in un’altra chat. Chiudi quella chat e riprova.': 'Lens is already active in another chat. Close that chat and try again.',
    'Cerchia qualsiasi cosa · Esc per uscire': 'Circle anything · Esc to exit',
    'Trascina i bordi per regolare · Invio per confermare': 'Drag edges to adjust · Enter to confirm',
    'Allineamento della selezione… · Esc per riprovare': 'Aligning selection… · Esc to retry',
    'ShakeSearch · Immagine e testo': 'ShakeSearch · Image and text',
    'Impossibile aprire l’immagine selezionata.': 'Unable to open the selected image.',
    'Riduci a icona': 'Minimize',
    'Ingrandisci / Ripristina': 'Maximize / Restore',
    'Chiudi': 'Close',
    'Lettura del testo…': 'Reading text…',
    'Adatta': 'Fit',
    'Il testo riconosciuto apparirà qui. Puoi modificarlo prima di copiarlo.': 'Recognized text will appear here. You can edit it before copying.',
    'Rileggi testo': 'Read text again',
    'Copia testo': 'Copy text',
    'Copia la parte selezionata oppure tutto il testo. Puoi usare anche Ctrl+C.': 'Copy the selected part or all text. You can also use Ctrl+C.',
    'Lettura non riuscita: ': 'Reading failed: ',
    'Testo parziale: prova con un’area più piccola. Puoi copiare la parte estratta.': 'Partial text: try a smaller area. You can copy the extracted part.',
    'Seleziona o correggi il testo, poi copialo. Ctrl+C copia la selezione.': 'Select or edit the text, then copy it. Ctrl+C copies the selection.',
    'Nessun testo riconosciuto. Prova con un’immagine più nitida.': 'No text recognized. Try a clearer image.',
    'Testo copiato negli appunti.': 'Text copied to clipboard.',
    'Configura GROQ_API_KEY nel file .env e riapri la finestra.': 'Configure GROQ_API_KEY in the .env file and reopen the window.',
    'Impossibile aprire la cattura dello schermo. Dettagli: ': 'Unable to open screen capture. Details: ',
    'Impossibile aprire la chat. Dettagli: ': 'Unable to open chat. Details: ',
    'Errore: ': 'Error: ',
    'Nota: ': 'Note: ',
    'Impossibile salvare la lingua. Controlla i permessi della cartella delle preferenze.': 'Unable to save the language. Check permissions for the preferences folder.',
}
IT = {value: key for key, value in EN.items()}


def settings_path():
    return Path(os.getenv('LOCALAPPDATA') or tempfile.gettempdir()) / 'ShakeSearch' / 'settings.json'


def read_settings():
    try:
        value = json.loads(settings_path().read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def get_language():
    value = read_settings().get('language', 'it')
    return value if value in ('it', 'en') else 'it'


def set_language(language):
    if language not in ('it', 'en'):
        raise ValueError('Unsupported language')
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    settings = dict(read_settings(), language=language)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            json.dump(settings, output, ensure_ascii=False)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def catalog(language):
    return {source: target if language == 'en' else source for source, target in EN.items()}


def tr(text, language=None):
    if (language or get_language()) == 'en':
        return EN.get(text, text)
    return IT.get(text, text)


def response_language(language):
    return 'Always answer in English.' if language == 'en' else 'Rispondi sempre in italiano.'


def google_language_url(url, language):
    parts = urlsplit(url)
    parameters = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != 'hl']
    parameters.append(('hl', language))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(parameters), parts.fragment))
