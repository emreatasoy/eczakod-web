"""ilacfiyati.com ürün listesini çeker ve fiyat dönüştürücünün okuduğu tek dosyada birleştirir.
Site sahibinin izniyle (2026-10-16). Saniyede en çok bir istek atar.

    python tools/ilacfiyati_cek.py --cikti ham            # tara + birleştir
    python tools/ilacfiyati_cek.py --cikti ham --birlestir   # yalnız birleştir

Sonra: python tools/fiyat_guncelle.py ham/ilacfiyati.jsonl

Sayfalarda arama motorları için JSON-LD ürün listesi var (barkod, ad, firma, fiyat); ürün sayfaları açılmaz.
Site her listede sayfalamayı 1000. sayfada kesip ilk sayfayı döndürüyor. İlaç listesi bundan büyük, bu yüzden
ilaçlar sitenin 14 ana grubundan çekilir; her biri 1000 sayfanın altında, toplamları tüm ilaçlar.
Kaldığı yerden devam eder: ham/ altındaki dosyada bulunan sayfalar yeniden istenmez.
Ham dosyalar --cikti klasörüne yazılır; git'e girmez.
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

SITE = 'https://ilacfiyati.com'
UA = 'EczaKod-fiyat/0.1 (+https://emreatasoy.github.io/eczakod-web/)'
DELAY = 1.0
OUT_DIR = Path('ham')

# 12 "Tüm …" grubu + alt grubu olmayan Duyu Organları ve Çeşitli İlaçlar.
ILAC_GRUPLARI = [
    'ilaclar/sindirim-sistemi-ve-metabolizma',
    'ilaclar/kan-ve-kan-yapici-organlar',
    'ilaclar/kalp-damar-sistemi',
    'ilaclar/dermatolojik-ilaclar',
    'ilaclar/urogenital-sistem-ve-cinsiyet-hormonlari',
    'ilaclar/endokrin-sistem',
    'ilaclar/enfeksiyona-karsi-kullanilan-ilaclar',
    'ilaclar/antineoplastik-ve-immunomodulator-ajanlar',
    'ilaclar/kas-iskelet-sistemi',
    'ilaclar/sinir-sistemi',
    'ilaclar/parazit-ve-bocek-ilaclari',
    'ilaclar/solunum-sistemi',
    'ilaclar/duyu-organlari',
    'ilaclar/cesitli-ilaclar',
]
LISTELER = ['takviye-edici-gida', 'kozmetik', *ILAC_GRUPLARI]


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Encoding': 'identity'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode('utf-8', errors='ignore')


def parse(html: str):
    """Sayfadaki ItemList: (sitedeki toplam ürün, bu sayfanın ürünleri) ya da (0, None)."""
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        if '"ItemList"' not in block:
            continue
        d = json.loads(block)
        out = []
        for el in d.get('itemListElement', []):
            it = el.get('item', {})
            offer = it.get('offers') or {}
            out.append({
                'barcode': str(it.get('identifier') or '').strip(),
                'name': (it.get('name') or '').strip(),
                'firm': ((it.get('manufacturer') or {}).get('name') or '').strip(),
                'price': offer.get('price'),
                'type': urlparse(it.get('url', '')).path.strip('/').split('/')[0],
                'url': it.get('url'),
            })
        return int(d.get('numberOfItems') or 0), out
    return 0, None


def crawl(path: str) -> int:
    """Bir listeyi sayfa sayfa çeker. 0: tamam, 5: sayfalama sınırı, diğerleri hata."""
    out = OUT_DIR / (path.replace('/', '-') + '.jsonl')
    done = set()
    first_urls = None
    if out.exists():
        for line in out.read_text(encoding='utf-8').splitlines():
            if line.strip():
                page = json.loads(line)
                done.add(page['pg'])
                if page['pg'] == 1:
                    first_urls = [i['url'] for i in page['items']]
    print(f'== {path} ({len(done)} sayfa önceden var)', flush=True)
    last, pg, fails = None, 1, 0
    with out.open('a', encoding='utf-8') as f:
        while last is None or pg <= last:
            if pg in done and last is not None:
                pg += 1
                continue
            t0 = time.time()
            try:
                total, items = parse(fetch(f'{SITE}/{path}?pg={pg}'))
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    print(f'pg {pg}: erişim engellendi ({e.code}), duruyorum', flush=True)
                    return 2
                fails += 1
                wait = 30 if e.code == 429 else 5 * fails
                print(f'pg {pg}: HTTP {e.code}, {wait} sn bekleyip yeniden', flush=True)
                time.sleep(wait)
                if fails > 8:
                    return 3
                continue
            except Exception as e:  # ağ kesintisi
                fails += 1
                print(f'pg {pg}: {type(e).__name__} {e}, yeniden', flush=True)
                time.sleep(5 * fails)
                if fails > 8:
                    return 3
                continue
            fails = 0
            if items is None:
                print(f'pg {pg}: ürün listesi bulunamadı, duruyorum', flush=True)
                return 4
            if last is None:
                last = -(-total // max(len(items), 1)) if total else pg
            if not items:
                return 0
            urls = [i['url'] for i in items]
            if pg == 1:
                first_urls = urls
            elif urls == first_urls:
                print(f'pg {pg}: ilk sayfa tekrar geldi (sayfalama sınırı), {path} eksik kalabilir', flush=True)
                return 5
            if pg not in done:
                f.write(json.dumps({'pg': pg, 'items': items}, ensure_ascii=False) + '\n')
                f.flush()
            if pg % 50 == 0:
                print(f'pg {pg}/{last}', flush=True)
            pg += 1
            time.sleep(max(0.0, DELAY - (time.time() - t0)))
    return 0


def merge() -> Path:
    """Liste dosyalarını adrese göre tekilleştirip tek dosyada toplar (fiyat_listesi.py okur)."""
    files = [OUT_DIR / (path.replace('/', '-') + '.jsonl') for path in LISTELER]
    missing = [f.name for f in files if not f.exists()]
    if missing:
        # Eksik listeyle yazılırsa eski tam dosya küçülür; birleştirme yapılmaz.
        raise SystemExit(f'birleştirilmedi, eksik liste: {", ".join(missing)}')
    by_url = {}
    for f in files:
        for line in f.read_text(encoding='utf-8').splitlines():
            if line.strip():
                for i in json.loads(line)['items']:
                    by_url.setdefault(i['url'], i)
    items = list(by_url.values())
    out = OUT_DIR / 'ilacfiyati.jsonl'
    out.write_text(json.dumps({'pg': 0, 'items': items}, ensure_ascii=False) + '\n', encoding='utf-8')
    kinds = {}
    for i in items:
        kinds[i['type']] = kinds.get(i['type'], 0) + 1
    print(f'{out}: {len(items)} ürün {kinds}', file=sys.stderr)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--birlestir', action='store_true', help='taramadan yalnız birleştir')
    ap.add_argument('--cikti', default='ham', help='ham dosyaların klasörü')
    args = ap.parse_args()
    global OUT_DIR
    OUT_DIR = Path(args.cikti)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not args.birlestir:
        for path in LISTELER:
            code = crawl(path)
            if code not in (0, 5):
                print(f'tarama durdu ({code}); yeniden çalıştırınca kaldığı yerden sürer', file=sys.stderr)
                return code
    merge()
    return 0


if __name__ == '__main__':
    sys.exit(main())
