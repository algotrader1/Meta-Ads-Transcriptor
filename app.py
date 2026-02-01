#!/usr/bin/env python3
"""
Facebook Ads Analyzer - Interface Web Moderne
"""

import os
import sys
import subprocess
import json
import re
import asyncio
import threading
from pathlib import Path
from datetime import datetime
from difflib import SequenceMatcher
from dataclasses import dataclass, asdict
from typing import Optional

from flask import Flask, render_template_string, jsonify, request, send_file

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY

app = Flask(__name__)

BASE_DIR = Path(__file__).parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
AUDIO_DIR = BASE_DIR / "audio"
TRANSCRIPTS_DIR = BASE_DIR / "transcripts"
RESULTS_DIR = BASE_DIR / "results"

progress_data = {
    "status": "idle",
    "current_step": 0,
    "total_steps": 5,
    "step_name": "",
    "detail": "",
    "progress": 0,
    "total": 0,
    "result": None
}

@dataclass
class PageInfo:
    page_id: str
    name: str = ""
    description: str = ""
    website: str = ""
    facebook_url: str = ""

@dataclass
class Ad:
    ad_id: str
    url: str
    start_date: Optional[datetime] = None
    video_path: Optional[Path] = None
    audio_path: Optional[Path] = None
    transcript: str = ""
    ad_text: str = ""
    cta_text: str = ""
    cta_link: str = ""
    duration_days: int = 0
    performance_score: float = 0.0
    is_original: bool = True
    similar_to: Optional[str] = None
    similarity_ratio: float = 0.0


def setup():
    for d in [DOWNLOADS_DIR, AUDIO_DIR, TRANSCRIPTS_DIR, RESULTS_DIR]:
        d.mkdir(exist_ok=True)


HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ads Analyzer</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Inter', -apple-system, sans-serif;
            background: #fafafa;
            min-height: 100vh;
            color: #1a1a1a;
        }

        .app {
            max-width: 900px;
            margin: 0 auto;
            padding: 40px 24px;
        }

        .header {
            text-align: center;
            margin-bottom: 40px;
        }

        .logo {
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 3px;
            text-transform: uppercase;
            color: #888;
            margin-bottom: 16px;
        }

        h1 {
            font-size: 36px;
            font-weight: 300;
            letter-spacing: -1px;
        }

        .form-section {
            background: white;
            border-radius: 16px;
            padding: 32px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
            border: 1px solid #eee;
            margin-bottom: 32px;
        }

        .form-row {
            display: flex;
            gap: 16px;
            align-items: flex-end;
        }

        .form-row .input-group { flex: 1; margin-bottom: 0; }

        .input-group {
            margin-bottom: 20px;
        }

        .input-group label {
            display: block;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #888;
            margin-bottom: 8px;
        }

        .input-group input, .input-group select {
            width: 100%;
            padding: 14px 16px;
            font-size: 15px;
            border: 2px solid #eee;
            border-radius: 10px;
            transition: all 0.2s;
            font-family: inherit;
            background: white;
        }

        .input-group input:focus, .input-group select:focus {
            outline: none;
            border-color: #1a1a1a;
        }

        .btn {
            padding: 14px 28px;
            background: #1a1a1a;
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            font-family: inherit;
            white-space: nowrap;
        }

        .btn:hover { background: #333; }
        .btn:disabled { opacity: 0.4; cursor: not-allowed; }

        .btn-outline {
            background: white;
            color: #1a1a1a;
            border: 2px solid #eee;
        }
        .btn-outline:hover { border-color: #ccc; background: white; }

        /* Progress */
        .progress-section {
            display: none;
            background: white;
            border-radius: 16px;
            padding: 32px;
            border: 1px solid #eee;
            margin-bottom: 32px;
        }

        .progress-section.active { display: block; }

        .steps {
            display: flex;
            justify-content: space-between;
            margin-bottom: 24px;
        }

        .step {
            display: flex;
            flex-direction: column;
            align-items: center;
            flex: 1;
        }

        .step-icon {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            background: #f0f0f0;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
            margin-bottom: 8px;
            transition: all 0.3s;
        }

        .step.active .step-icon {
            background: #1a1a1a;
            color: white;
            animation: pulse 1.5s infinite;
        }

        .step.done .step-icon {
            background: #22c55e;
            color: white;
        }

        .step-label {
            font-size: 10px;
            font-weight: 500;
            color: #aaa;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .step.active .step-label, .step.done .step-label { color: #1a1a1a; }

        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.1); }
        }

        .progress-info {
            text-align: center;
            padding: 20px;
            background: #f8f8f8;
            border-radius: 10px;
        }

        .progress-info h3 { font-size: 16px; margin-bottom: 4px; }
        .progress-info p { color: #888; font-size: 13px; }

        /* Results */
        .results-section {
            display: none;
        }

        .results-section.active { display: block; }

        .results-header {
            background: white;
            border-radius: 16px;
            padding: 32px;
            border: 1px solid #eee;
            margin-bottom: 24px;
            text-align: center;
        }

        .results-header h2 {
            font-size: 24px;
            font-weight: 600;
            margin-bottom: 4px;
        }

        .results-header .subtitle {
            color: #888;
            margin-bottom: 24px;
        }

        .stats {
            display: flex;
            justify-content: center;
            gap: 48px;
            margin-bottom: 24px;
        }

        .stat-value {
            font-size: 36px;
            font-weight: 700;
        }

        .stat-label {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #888;
        }

        .actions {
            display: flex;
            gap: 12px;
            justify-content: center;
        }

        /* Scripts */
        .scripts-list {
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .script-card {
            background: white;
            border-radius: 12px;
            border: 1px solid #eee;
            overflow: hidden;
        }

        .script-header {
            padding: 16px 20px;
            border-bottom: 1px solid #f0f0f0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .script-rank {
            font-weight: 700;
            font-size: 14px;
        }

        .script-badge {
            font-size: 11px;
            padding: 4px 10px;
            border-radius: 20px;
            font-weight: 600;
        }

        .badge-original {
            background: #dcfce7;
            color: #166534;
        }

        .badge-variant {
            background: #fef3c7;
            color: #92400e;
        }

        .badge-unique {
            background: #e0e7ff;
            color: #3730a3;
        }

        .script-body {
            padding: 20px;
        }

        .script-text {
            font-size: 14px;
            line-height: 1.7;
            color: #333;
            background: #f8f8f8;
            padding: 16px;
            border-radius: 8px;
            margin-bottom: 12px;
        }

        .script-meta {
            font-size: 12px;
            color: #888;
        }

        .script-meta a {
            color: #0066cc;
            text-decoration: none;
        }

        .script-meta a:hover { text-decoration: underline; }

        .script-details {
            margin-top: 12px;
            padding-top: 12px;
            border-top: 1px solid #f0f0f0;
            font-size: 12px;
            color: #666;
        }

        .script-details strong { color: #444; }

        .error-box {
            display: none;
            padding: 16px;
            background: #fef2f2;
            border: 1px solid #fecaca;
            border-radius: 10px;
            color: #dc2626;
            font-size: 14px;
            margin-bottom: 20px;
        }

        .error-box.active { display: block; }

        .copy-btn {
            background: none;
            border: 1px solid #ddd;
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 11px;
            cursor: pointer;
            color: #666;
        }

        .copy-btn:hover { border-color: #999; color: #333; }
    </style>
</head>
<body>
    <div class="app">
        <header class="header">
            <div class="logo">Ads Analyzer</div>
            <h1>Transcription de publicités</h1>
        </header>

        <div class="form-section" id="formSection">
            <form id="analyzeForm">
                <div class="form-row">
                    <div class="input-group">
                        <label>URL Facebook ou Instagram</label>
                        <input type="text" id="pageUrl"
                               placeholder="facebook.com/pagename ou instagram.com/username"
                               required>
                    </div>
                    <div class="input-group" style="width: 140px; flex: none;">
                        <label>Langue</label>
                        <select id="language">
                            <option value="en">English</option>
                            <option value="fr">Français</option>
                            <option value="es">Español</option>
                            <option value="de">Deutsch</option>
                        </select>
                    </div>
                    <button type="submit" class="btn" id="submitBtn">Analyser</button>
                </div>
            </form>
            <div class="error-box" id="errorBox"></div>
        </div>

        <div class="progress-section" id="progressSection">
            <div class="steps">
                <div class="step" data-step="1">
                    <div class="step-icon">🔍</div>
                    <span class="step-label">Scan</span>
                </div>
                <div class="step" data-step="2">
                    <div class="step-icon">⬇️</div>
                    <span class="step-label">Download</span>
                </div>
                <div class="step" data-step="3">
                    <div class="step-icon">🎙️</div>
                    <span class="step-label">Transcribe</span>
                </div>
                <div class="step" data-step="4">
                    <div class="step-icon">🔬</div>
                    <span class="step-label">Analyze</span>
                </div>
                <div class="step" data-step="5">
                    <div class="step-icon">📄</div>
                    <span class="step-label">Report</span>
                </div>
            </div>
            <div class="progress-info">
                <h3 id="progressTitle">Initialisation...</h3>
                <p id="progressDetail">Préparation</p>
            </div>
        </div>

        <div class="results-section" id="resultsSection">
            <div class="results-header">
                <h2 id="resultPageName">-</h2>
                <p class="subtitle" id="resultPageDesc">Analyse terminée</p>
                <div class="stats">
                    <div class="stat">
                        <div class="stat-value" id="statTotal">0</div>
                        <div class="stat-label">Scripts</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value" id="statUnique">0</div>
                        <div class="stat-label">Uniques</div>
                    </div>
                </div>
                <div class="actions">
                    <a href="#" class="btn" id="downloadBtn">📥 Télécharger PDF</a>
                    <button class="btn btn-outline" onclick="newAnalysis()">Nouvelle analyse</button>
                </div>
            </div>

            <div class="scripts-list" id="scriptsList"></div>
        </div>
    </div>

    <script>
        let pollInterval = null;

        document.getElementById('analyzeForm').addEventListener('submit', async (e) => {
            e.preventDefault();

            const pageUrl = document.getElementById('pageUrl').value;
            const language = document.getElementById('language').value;

            document.getElementById('errorBox').classList.remove('active');
            document.getElementById('resultsSection').classList.remove('active');
            document.getElementById('progressSection').classList.add('active');
            document.getElementById('submitBtn').disabled = true;

            document.querySelectorAll('.step').forEach(s => s.classList.remove('active', 'done'));

            try {
                const response = await fetch('/analyze', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ pageUrl, language })
                });

                const data = await response.json();
                if (data.error) throw new Error(data.error);

                pollInterval = setInterval(checkProgress, 800);

            } catch (error) {
                showError(error.message);
            }
        });

        async function checkProgress() {
            try {
                const response = await fetch('/progress');
                const data = await response.json();

                document.querySelectorAll('.step').forEach(s => {
                    const stepNum = parseInt(s.dataset.step);
                    s.classList.remove('active', 'done');
                    if (stepNum < data.current_step) s.classList.add('done');
                    if (stepNum === data.current_step) s.classList.add('active');
                });

                document.getElementById('progressTitle').textContent = data.step_name;
                document.getElementById('progressDetail').textContent = data.detail;

                if (data.status === 'complete') {
                    clearInterval(pollInterval);
                    showResults(data.result);
                } else if (data.status === 'error') {
                    clearInterval(pollInterval);
                    showError(data.detail);
                }
            } catch (e) { console.error(e); }
        }

        function showResults(result) {
            document.getElementById('progressSection').classList.remove('active');
            document.getElementById('resultsSection').classList.add('active');
            document.getElementById('submitBtn').disabled = false;

            document.getElementById('resultPageName').textContent = result.page_name;
            document.getElementById('resultPageDesc').textContent = result.page_description || 'Analyse terminée';
            document.getElementById('statTotal').textContent = result.total_scripts;
            document.getElementById('statUnique').textContent = result.unique_scripts;
            document.getElementById('downloadBtn').href = '/download/' + result.filename;

            // Render scripts
            const list = document.getElementById('scriptsList');
            list.innerHTML = result.scripts.map((script, i) => `
                <div class="script-card">
                    <div class="script-header">
                        <span class="script-rank">#${i + 1} · Score ${script.score}</span>
                        <span class="script-badge ${script.is_original ? (script.variants > 0 ? 'badge-original' : 'badge-unique') : 'badge-variant'}">
                            ${script.is_original ? (script.variants > 0 ? 'ORIGINAL · ' + script.variants + ' variante(s)' : 'UNIQUE') : 'VARIANTE ' + script.similarity + '%'}
                        </span>
                    </div>
                    <div class="script-body">
                        <div class="script-text">${script.transcript}</div>
                        <div class="script-meta">
                            <a href="${script.url}" target="_blank">Voir la publicité →</a>
                            ${script.duration ? ' · ' + script.duration + ' jours' : ''}
                            <button class="copy-btn" onclick="copyScript(this, ${i})" style="float: right;">Copier</button>
                        </div>
                        ${script.ad_text || script.cta_text ? `
                        <div class="script-details">
                            ${script.ad_text ? '<strong>Texte:</strong> ' + script.ad_text.substring(0, 150) + '...<br>' : ''}
                            ${script.cta_text ? '<strong>CTA:</strong> ' + script.cta_text : ''}
                            ${script.cta_link ? ' · <a href="' + script.cta_link + '" target="_blank">Lien</a>' : ''}
                        </div>
                        ` : ''}
                    </div>
                </div>
            `).join('');
        }

        function copyScript(btn, index) {
            const scripts = document.querySelectorAll('.script-text');
            const text = scripts[index].textContent;
            navigator.clipboard.writeText(text);
            btn.textContent = 'Copié !';
            setTimeout(() => btn.textContent = 'Copier', 2000);
        }

        function showError(msg) {
            document.getElementById('progressSection').classList.remove('active');
            document.getElementById('errorBox').textContent = msg;
            document.getElementById('errorBox').classList.add('active');
            document.getElementById('submitBtn').disabled = false;
        }

        function newAnalysis() {
            document.getElementById('resultsSection').classList.remove('active');
            document.getElementById('pageUrl').value = '';
            document.querySelectorAll('.step').forEach(s => s.classList.remove('active', 'done'));
        }
    </script>
</body>
</html>
'''


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/analyze', methods=['POST'])
def analyze():
    global progress_data

    data = request.json
    page_url = data.get('pageUrl', '').strip()
    language = data.get('language', 'en')

    page_id = None
    page_name_to_search = None

    # Check for view_all_page_id parameter
    match = re.search(r'view_all_page_id=(\d+)', page_url)
    if match:
        page_id = match.group(1)
    # Check for profile.php?id=XXXXX format
    elif 'profile.php' in page_url:
        profile_match = re.search(r'[?&]id=(\d+)', page_url)
        if profile_match:
            page_id = profile_match.group(1)
    # Check for ads library ?id= format
    elif '/ads/library/' in page_url and '?id=' in page_url:
        ad_match = re.search(r'\?id=(\d+)', page_url)
        if ad_match:
            # This is a single ad URL, we need to find its page
            page_name_to_search = None
            page_id = None
            # Will need special handling
    elif page_url.isdigit():
        page_id = page_url
    elif 'facebook.com/' in page_url:
        fb_match = re.search(r'facebook\.com/([^/?#]+)', page_url)
        if fb_match and fb_match.group(1) not in ['ads', 'profile.php', 'watch', 'reel']:
            page_name_to_search = fb_match.group(1)
    elif 'instagram.com/' in page_url:
        ig_match = re.search(r'instagram\.com/([^/?]+)', page_url)
        if ig_match:
            page_name_to_search = ig_match.group(1)
    elif page_url and not page_url.startswith('http'):
        page_name_to_search = page_url

    if not page_id and not page_name_to_search:
        return jsonify({"error": "URL invalide. Entrez une URL Facebook ou Instagram."})

    progress_data = {
        "status": "running",
        "current_step": 1,
        "total_steps": 5,
        "step_name": "Recherche de la page",
        "detail": "Connexion...",
        "progress": 0,
        "total": 0,
        "result": None
    }

    thread = threading.Thread(target=run_analysis, args=(page_id, language, page_name_to_search))
    thread.start()

    return jsonify({"success": True})


@app.route('/progress')
def get_progress():
    return jsonify(progress_data)


@app.route('/download/<filename>')
def download(filename):
    filepath = RESULTS_DIR / filename
    if filepath.exists():
        return send_file(filepath, as_attachment=True)
    return "File not found", 404


def update_progress(step, name, detail="", progress=0, total=0):
    global progress_data
    progress_data["current_step"] = step
    progress_data["step_name"] = name
    progress_data["detail"] = detail
    progress_data["progress"] = progress
    progress_data["total"] = total


def run_analysis(page_id: str, language: str, page_name_to_search: str = None):
    global progress_data

    try:
        setup()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        if not page_id and page_name_to_search:
            update_progress(1, "Recherche de la page", f"'{page_name_to_search}'...")
            page_id = loop.run_until_complete(find_page_id(page_name_to_search))
            if not page_id:
                raise Exception(f"Page '{page_name_to_search}' non trouvée")

        result = loop.run_until_complete(analyze_page(page_id, language))
        loop.close()

        progress_data["status"] = "complete"
        progress_data["result"] = result

    except Exception as e:
        progress_data["status"] = "error"
        progress_data["detail"] = str(e)


async def find_page_id(page_name: str) -> str:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})

        try:
            search_url = f"https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=ALL&q={page_name}&search_type=keyword_unordered"
            await page.goto(search_url, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(3)

            html = await page.content()

            match = re.search(r'view_all_page_id=(\d+)', html)
            if match:
                return match.group(1)

            match2 = re.search(r'"page_id":"(\d+)"', html)
            if match2:
                return match2.group(1)

            return None
        finally:
            await browser.close()


async def analyze_page(page_id: str, language: str):
    from playwright.async_api import async_playwright

    update_progress(1, "Scan des publicités", "Connexion...")

    page_info = PageInfo(page_id=page_id)
    ads_data = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})

        try:
            url = f"https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=ALL&view_all_page_id={page_id}&media_type=video"
            await page.goto(url, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(3)

            html = await page.content()

            name_match = re.search(r'"page_name":"([^"]+)"', html)
            if name_match:
                page_info.name = name_match.group(1)

            page_info.facebook_url = f"https://www.facebook.com/{page_id}"

            desc_match = re.search(r'"page_description":"([^"]*)"', html)
            if desc_match:
                try:
                    page_info.description = desc_match.group(1).encode().decode('unicode_escape')
                except:
                    page_info.description = desc_match.group(1)

            website_match = re.search(r'"website":"([^"]*)"', html)
            if website_match:
                page_info.website = website_match.group(1)

            update_progress(1, "Scan des publicités", page_info.name or "Chargement...")

            last_height = 0
            for i in range(30):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)
                new_height = await page.evaluate("document.body.scrollHeight")
                update_progress(1, "Scan des publicités", f"Chargement ({i+1})", i+1, 30)
                if new_height == last_height:
                    break
                last_height = new_height

            html = await page.content()

            patterns = [r'"adArchiveID":"(\d+)"', r'"ad_archive_id":"(\d+)"']
            all_ids = set()
            for pattern in patterns:
                all_ids.update(re.findall(pattern, html))

            ad_ids = [id for id in all_ids if len(id) >= 12]
            update_progress(1, "Scan", f"{len(ad_ids)} pubs trouvées")

            for ad_id in ad_ids:
                ad_data = {
                    "ad_id": ad_id,
                    "url": f"https://www.facebook.com/ads/library/?id={ad_id}",
                    "start_date": None,
                    "ad_text": "",
                    "cta_text": "",
                    "cta_link": ""
                }

                date_match = re.search(rf'{ad_id}.*?Started running on (\w+ \d+, \d{{4}})', html, re.DOTALL)
                if date_match:
                    try:
                        ad_data["start_date"] = datetime.strptime(date_match.group(1), "%b %d, %Y")
                    except:
                        pass

                text_pattern = rf'"adArchiveID":"{ad_id}".*?"body_markup":\{{"markup":"([^"]*)"'
                text_match = re.search(text_pattern, html, re.DOTALL)
                if text_match:
                    try:
                        ad_data["ad_text"] = text_match.group(1).encode().decode('unicode_escape')[:500]
                    except:
                        ad_data["ad_text"] = text_match.group(1)[:500]

                cta_pattern = rf'"adArchiveID":"{ad_id}".*?"cta_text":"([^"]*)".*?"link_url":"([^"]*)"'
                cta_match = re.search(cta_pattern, html, re.DOTALL)
                if cta_match:
                    ad_data["cta_text"] = cta_match.group(1)
                    ad_data["cta_link"] = cta_match.group(2)

                ads_data.append(ad_data)

        finally:
            await browser.close()

    if not ads_data:
        raise Exception("Aucune publicité trouvée")

    ads = [Ad(
        ad_id=d["ad_id"], url=d["url"], start_date=d.get("start_date"),
        ad_text=d.get("ad_text", ""), cta_text=d.get("cta_text", ""), cta_link=d.get("cta_link", "")
    ) for d in ads_data]

    update_progress(2, "Téléchargement", f"0/{len(ads)}", 0, len(ads))

    for i, ad in enumerate(ads):
        update_progress(2, "Téléchargement", f"{i+1}/{len(ads)}", i+1, len(ads))
        output_path = DOWNLOADS_DIR / f"ad_{ad.ad_id}.mp4"

        if output_path.exists() and output_path.stat().st_size > 1000:
            ad.video_path = output_path
        else:
            cmd = ["yt-dlp", "-f", "best[ext=mp4]/best", "-o", str(output_path),
                   "--no-playlist", "--quiet", "--no-warnings", ad.url]
            try:
                subprocess.run(cmd, capture_output=True, timeout=120)
                if output_path.exists():
                    ad.video_path = output_path
            except:
                pass

        if ad.video_path:
            audio_path = AUDIO_DIR / f"ad_{ad.ad_id}.mp3"
            if not audio_path.exists():
                cmd = ["ffmpeg", "-i", str(ad.video_path), "-vn", "-acodec", "libmp3lame",
                       "-q:a", "2", "-y", "-loglevel", "error", str(audio_path)]
                try:
                    subprocess.run(cmd, capture_output=True, timeout=60)
                except:
                    pass
            if audio_path.exists() and audio_path.stat().st_size > 1000:
                ad.audio_path = audio_path

    import whisper
    ads_with_audio = [a for a in ads if a.audio_path]
    update_progress(3, "Transcription", f"0/{len(ads_with_audio)}", 0, len(ads_with_audio))

    if ads_with_audio:
        model = whisper.load_model("base")
        for i, ad in enumerate(ads_with_audio):
            update_progress(3, "Transcription", f"{i+1}/{len(ads_with_audio)}", i+1, len(ads_with_audio))
            cache_file = TRANSCRIPTS_DIR / f"ad_{ad.ad_id}.txt"
            if cache_file.exists():
                ad.transcript = cache_file.read_text(encoding="utf-8")
            else:
                try:
                    result = model.transcribe(str(ad.audio_path), language=language)
                    ad.transcript = result["text"].strip()
                    if ad.transcript:
                        cache_file.write_text(ad.transcript, encoding="utf-8")
                except:
                    pass

    # Cleanup: delete video and audio files after transcription
    update_progress(3, "Transcription", "Nettoyage des fichiers...")
    for ad in ads:
        if ad.video_path and ad.video_path.exists():
            try:
                ad.video_path.unlink()
            except:
                pass
        if ad.audio_path and ad.audio_path.exists():
            try:
                ad.audio_path.unlink()
            except:
                pass

    update_progress(4, "Analyse", "Similarités...")

    ads_with_text = [a for a in ads if a.transcript]
    assigned = set()

    for i, ad1 in enumerate(ads_with_text):
        if ad1.ad_id in assigned:
            continue
        ad1.is_original = True
        assigned.add(ad1.ad_id)
        for ad2 in ads_with_text[i+1:]:
            if ad2.ad_id in assigned:
                continue
            ratio = SequenceMatcher(None, ad1.transcript.lower(), ad2.transcript.lower()).ratio()
            if ratio >= 0.6:
                ad2.is_original = False
                ad2.similar_to = ad1.ad_id
                ad2.similarity_ratio = ratio
                assigned.add(ad2.ad_id)

    variant_counts = {}
    for ad in ads:
        if ad.similar_to:
            variant_counts[ad.similar_to] = variant_counts.get(ad.similar_to, 0) + 1

    for ad in ads:
        score = 30
        if ad.start_date:
            ad.duration_days = (datetime.now() - ad.start_date).days
            if ad.duration_days >= 90: score = 100
            elif ad.duration_days >= 60: score = 80
            elif ad.duration_days >= 30: score = 60
            elif ad.duration_days >= 14: score = 40
            else: score = 20
        if ad.is_original: score += 20
        if ad.ad_id in variant_counts: score += variant_counts[ad.ad_id] * 15
        ad.performance_score = score

    update_progress(5, "Rapport", "Génération PDF...")

    pdf_path = generate_pdf(ads, page_info, variant_counts)

    ads_sorted = sorted([a for a in ads if a.transcript], key=lambda x: (-x.performance_score, -x.duration_days))

    scripts_data = []
    for ad in ads_sorted:
        scripts_data.append({
            "transcript": ad.transcript,
            "url": ad.url,
            "score": int(ad.performance_score),
            "duration": ad.duration_days if ad.start_date else None,
            "is_original": ad.is_original,
            "variants": variant_counts.get(ad.ad_id, 0),
            "similarity": int(ad.similarity_ratio * 100) if ad.similarity_ratio else 0,
            "ad_text": ad.ad_text,
            "cta_text": ad.cta_text,
            "cta_link": ad.cta_link
        })

    return {
        "total_scripts": len(ads_with_text),
        "unique_scripts": len([a for a in ads_with_text if a.is_original]),
        "filename": pdf_path.name,
        "page_name": page_info.name or f"Page {page_id}",
        "page_description": page_info.description[:200] if page_info.description else "",
        "scripts": scripts_data
    }


def generate_pdf(ads, page_info: PageInfo, variant_counts):
    ads_with_transcript = sorted(
        [a for a in ads if a.transcript],
        key=lambda x: (-x.performance_score, -x.duration_days)
    )

    safe_name = re.sub(r'[^\w\s-]', '', page_info.name or page_info.page_id).strip().replace(' ', '_')[:30]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_path = RESULTS_DIR / f"{safe_name}_{len(ads_with_transcript)}_scripts_{timestamp}.pdf"

    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('Title', fontSize=32, textColor=colors.HexColor('#1a1a1a'), spaceAfter=8, alignment=TA_CENTER, fontName='Helvetica-Bold')
    subtitle_style = ParagraphStyle('Subtitle', fontSize=11, textColor=colors.HexColor('#666666'), spaceAfter=6, alignment=TA_CENTER, leading=16)
    section_style = ParagraphStyle('Section', fontSize=14, textColor=colors.HexColor('#1a1a1a'), spaceBefore=20, spaceAfter=12, fontName='Helvetica-Bold')
    ad_header_style = ParagraphStyle('AdHeader', fontSize=12, textColor=colors.HexColor('#1a1a1a'), spaceBefore=20, spaceAfter=4, fontName='Helvetica-Bold')
    script_style = ParagraphStyle('Script', fontSize=11, textColor=colors.HexColor('#1a1a1a'), alignment=TA_JUSTIFY, leading=17, fontName='Helvetica')
    link_style = ParagraphStyle('Link', fontSize=8, textColor=colors.HexColor('#0066cc'), spaceAfter=4)
    small_style = ParagraphStyle('Small', fontSize=9, textColor=colors.HexColor('#666666'), leading=13, spaceBefore=8)

    story = []
    story.append(Spacer(1, 2*cm))
    story.append(Paragraph(page_info.name or f"Page {page_info.page_id}", title_style))
    story.append(HRFlowable(width="30%", thickness=2, color=colors.HexColor('#1a1a1a'), spaceAfter=16, spaceBefore=16, hAlign='CENTER'))
    story.append(Paragraph("Analyse des publicités Facebook", subtitle_style))

    if page_info.description:
        desc = page_info.description[:300].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph(f"<i>{desc}...</i>", subtitle_style))

    story.append(Spacer(1, 1*cm))
    links_data = []
    if page_info.facebook_url:
        links_data.append(['Page Facebook', page_info.facebook_url])
    if page_info.website:
        links_data.append(['Site web', page_info.website])
    if links_data:
        links_table = Table(links_data, colWidths=[4*cm, 10*cm])
        links_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#666666')),
            ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#0066cc')),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(links_table)

    story.append(Spacer(1, 1.5*cm))
    unique_count = len([a for a in ads_with_transcript if a.is_original])
    stats_data = [
        ['SCRIPTS', 'UNIQUES', 'DATE'],
        [str(len(ads_with_transcript)), str(unique_count), datetime.now().strftime('%d/%m/%Y')]
    ]
    stats_table = Table(stats_data, colWidths=[4.5*cm, 4.5*cm, 4.5*cm])
    stats_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica'), ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9), ('FONTSIZE', (0, 1), (-1, 1), 24),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#888888')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(stats_table)
    story.append(PageBreak())

    story.append(Paragraph("Scripts publicitaires", section_style))

    for rank, ad in enumerate(ads_with_transcript, 1):
        vc = variant_counts.get(ad.ad_id, 0)
        badge = f"ORIGINAL · {vc} variante(s)" if ad.is_original and vc else ("UNIQUE" if ad.is_original else f"VARIANTE ({int(ad.similarity_ratio*100)}%)")
        date_str = f" · {ad.duration_days}j" if ad.start_date else ""

        story.append(Paragraph(f"#{rank} — Score {int(ad.performance_score)} · {badge}{date_str}", ad_header_style))
        story.append(Paragraph(f"<link href='{ad.url}'>{ad.url}</link>", link_style))

        script_text = ad.transcript.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        script_table = Table([[Paragraph(script_text, script_style)]], colWidths=[15*cm])
        script_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8f8f8')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e0e0')),
            ('TOPPADDING', (0, 0), (-1, -1), 14), ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
            ('LEFTPADDING', (0, 0), (-1, -1), 14), ('RIGHTPADDING', (0, 0), (-1, -1), 14),
        ]))
        story.append(Spacer(1, 0.2*cm))
        story.append(script_table)

        extra = []
        if ad.ad_text:
            extra.append(f"<b>Texte:</b> {ad.ad_text[:150].replace('&', '&amp;')}...")
        if ad.cta_text:
            extra.append(f"<b>CTA:</b> {ad.cta_text}")
        if extra:
            story.append(Paragraph("<br/>".join(extra), small_style))

        story.append(Spacer(1, 0.6*cm))
        if rank < len(ads_with_transcript):
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#e0e0e0'), spaceAfter=8))

    doc.build(story)
    return pdf_path


if __name__ == '__main__':
    setup()
    print("\n  Ads Analyzer → http://localhost:5001\n")
    import webbrowser
    webbrowser.open('http://localhost:5001')
    app.run(debug=False, port=5001, host='127.0.0.1')
