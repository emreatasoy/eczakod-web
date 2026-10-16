"""Yeni taramayı yayındaki fiyat listesine işler. Anahtar barkod.

    python tools/fiyat_guncelle.py ham/ilacfiyati.jsonl

- Yeni barkod → yeni kayıt (firstSeen bugün).
- Var olan barkod → ad, firma, tür güncellenir; fiyat değiştiyse priceDate bugün olur.
- Sitede fiyatsız görünen barkod → yürürlükten kalkmış sayılır, listeden çıkar.
- Taramada hiç görünmeyen barkod (site kaldırdı ya da barkodu bozuk girildi) → listede son fiyatıyla kalır,
  missingSince alanı ilk görünmediği günü tutar; yeniden görünürse alan silinir. Bu kayıtlar silinmez:
  liste zamanla birikir, ileride başka bir fiyat kaynağına geçilse de elde kalır.
Kayıtlara her çalışmada değişen alan yazılmaz; git farkında yalnızca gerçekten değişen ürünler görünür.
Tarama eksik görünüyorsa (ürün sayısı birden düştüyse) hiçbir şey yazılmaz ve hata ile çıkılır.

Çıktı: fiyat/fiyatlar.json (biçim: eczakod-fiyat v1) ve fiyat/surum.json (telefon önce buna bakar).
"""
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'fiyat' / 'fiyatlar.json'
VERSION_FILE = ROOT / 'fiyat' / 'surum.json'
MIN_RATIO = 0.9  # yeni taramadaki fiyatlı ürün sayısı öncekinin %90'ının altındaysa yayınlama
KINDS = {'ilaclar': 'ilac', 'takviye-edici-gida': 'takviye', 'kozmetik': 'kozmetik'}


def ean13_ok(code: str) -> bool:
    if not re.fullmatch(r'\d{13}', code):
        return False
    s = sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(code[:12]))
    return (10 - s % 10) % 10 == int(code[12])


def gtin13(code: str) -> str | None:
    """EAN-13'ü olduğu gibi, 12 haneli UPC-A'yı başına 0 ekleyerek döner; geçersizse None."""
    if re.fullmatch(r'\d{12}', code):
        code = '0' + code
    return code if ean13_ok(code) else None


def clean(v) -> str:
    return re.sub(r'\s+', ' ', str(v or '')).strip()


def read_crawl(path: Path):
    """Tarama → (fiyatlı ürünler {barkod: kayıt}, fiyatsız barkodlar)."""
    priced, unpriced = {}, set()
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        for i in json.loads(line)['items']:
            barcode = gtin13(clean(i.get('barcode')))
            if not barcode:
                continue
            try:
                price = round(float(i.get('price')), 2)
            except (TypeError, ValueError):
                price = 0
            if price <= 0:
                unpriced.add(barcode)
                continue
            if barcode in priced:
                continue
            item = {'barcode': barcode, 'name': clean(i.get('name'))}
            if clean(i.get('firm')):
                item['firm'] = clean(i.get('firm'))
            item['kind'] = KINDS.get(i.get('type'), 'diger')
            item['price'] = price
            priced[barcode] = item
    return priced, unpriced - set(priced)


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    today = dt.date.today().isoformat()
    priced, unpriced = read_crawl(Path(sys.argv[1]))

    old = {}
    if OUT.exists():
        doc = json.loads(OUT.read_text(encoding='utf-8'))
        old = {i['barcode']: i for i in doc['items']}
    old_live = sum(1 for i in old.values() if 'missingSince' not in i)
    if old and len(priced) < MIN_RATIO * old_live:
        raise SystemExit(f'tarama eksik görünüyor: {len(priced)} fiyatlı ürün, önceki {old_live}; yayınlanmadı')

    added = changed = removed = 0
    items = {}
    for barcode, new in priced.items():
        prev = old.get(barcode)
        item = dict(new)
        if prev is None:
            added += 1
            item['priceDate'] = today
            item['firstSeen'] = today
        else:
            item['firstSeen'] = prev.get('firstSeen', today)
            if prev.get('price') != new['price']:
                changed += 1
                item['priceDate'] = today
            elif prev.get('priceDate'):
                item['priceDate'] = prev['priceDate']
            for k in ('vat',):  # kaynakta olmayan ama elde olan alanlar korunur
                if k in prev:
                    item[k] = prev[k]
        items[barcode] = item
    for barcode, prev in old.items():
        if barcode in items:
            continue
        if barcode in unpriced:
            removed += 1  # sitede fiyatsız: yürürlükten kalkmış
            continue
        # Bu taramada görünmedi; son bilinen fiyatıyla kalır.
        items[barcode] = {**prev, 'missingSince': prev.get('missingSince', today)}

    ordered = [items[k] for k in sorted(items)]
    kinds = {}
    for i in ordered:
        kinds[i['kind']] = kinds.get(i['kind'], 0) + 1
    doc = {
        'format': 'eczakod-fiyat',
        'version': 1,
        'listDate': today,
        'generatedAt': dt.datetime.now(dt.timezone(dt.timedelta(hours=3))).replace(microsecond=0).isoformat(),
        'currency': 'TRY',
        'count': len(ordered),
        'sources': [{'name': 'ILACFIYATI', 'listDate': today, 'count': len(priced)}],
        'items': ordered,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Her ürün tek satırda: git farkında yalnızca değişen ürünler görünsün.
    head = {k: v for k, v in doc.items() if k != 'items'}
    lines = [json.dumps(i, ensure_ascii=False, separators=(',', ':')) for i in ordered]
    text = json.dumps(head, ensure_ascii=False, indent=2)[:-2] + ',\n  "items": [\n    ' + ',\n    '.join(lines) + '\n  ]\n}\n'
    json.loads(text)
    OUT.write_text(text, encoding='utf-8', newline='\n')
    VERSION_FILE.write_text(json.dumps({
        'format': 'eczakod-fiyat-surum',
        'version': 1,
        'listDate': today,
        'generatedAt': doc['generatedAt'],
        'count': len(ordered),
        'kinds': kinds,
        'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
        'file': 'fiyatlar.json',
        'changes': {'added': added, 'priceChanged': changed, 'removed': removed},
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f'{len(ordered)} ürün {kinds}; yeni {added}, fiyatı değişen {changed}, çıkan {removed}')


if __name__ == '__main__':
    main()
