"""Optional Chromium check. Google requests are intercepted; this does not verify Lens itself.

Install Playwright and its Chromium browser, then run this script from the checkout.
Set CHROMIUM_EXECUTABLE to use an existing Chromium installation.
"""
import io
import os
from pathlib import Path
from email import policy
from email.parser import BytesParser
import sys
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright
from lens_handoff import LensHandoff

output=io.BytesIO()
image=Image.new('RGB',(320,200),'white')
ImageDraw.Draw(image).rectangle((40,40,280,160),outline='orange',width=8)
image.save(output,'PNG')
question='Dove trovo questo? è arancione </script><script>alert(1)</script>'
with patch('lens_handoff.webbrowser.open',return_value=True):
    handoff=LensHandoff(output.getvalue(),question); handoff.open()
try:
    with sync_playwright() as runner:
        browser=runner.chromium.launch(executable_path=os.getenv('CHROMIUM_EXECUTABLE') or None,headless=True,args=['--no-sandbox'])
        page=browser.new_page()
        captured=[];dialogs=[]
        page.on('dialog',lambda dialog: (dialogs.append(dialog.message),dialog.dismiss()))
        def receive(route):
            request=route.request
            captured.append((request.url,request.headers,request.post_data_buffer))
            route.fulfill(status=200,content_type='text/html',body='<html><title>Upload captured</title><body>Simulated Lens receiver</body></html>')
        page.route('https://lens.google/**',receive)
        page.goto(handoff.url)
        page.wait_for_url('https://lens.google/**')
        assert len(captured)==1,captured
        url,headers,body=captured[0]
        assert parse_qs(urlsplit(url).query)['q']==[question]
        message=BytesParser(policy=policy.default).parsebytes(('Content-Type: '+headers['content-type']+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+body)
        parts={part.get_param('name',header='content-disposition'):part for part in message.iter_parts()}
        assert parts['encoded_image'].get_filename()=='shakesearch.png'
        decoded=Image.open(io.BytesIO(parts['encoded_image'].get_payload(decode=True)))
        assert decoded.size==(320,200)
        assert decoded.getpixel((40,40))==(255,165,0)
        assert parts['q'].get_payload(decode=True).decode('utf-8')==question
        assert not dialogs,dialogs
        print('PASS Chromium: auto navigation, multipart PNG pixels, question and HTML-injection safety')
        with patch('lens_handoff.webbrowser.open',return_value=True):
            fallback=LensHandoff(output.getvalue());fallback.open()
        try:
            other=browser.new_page()
            other.add_init_script('window.DataTransfer = class {constructor(){throw new Error("not supported")}}')
            other.goto(fallback.url)
            assert other.locator('#fallback').is_visible()
            assert other.locator('#save').get_attribute('download')=='shakesearch.png'
            print('PASS Chromium: manual fallback appears when browser upload is unavailable')
        finally:
            fallback.close()
        browser.close()
finally:
    handoff.close()
