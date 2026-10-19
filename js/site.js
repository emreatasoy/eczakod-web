// Menü, üst çubuk gölgesi, giriş sahnesi ve iletişim formu.
(function () {
  var ust = document.querySelector('.ust');
  var menu = document.getElementById('menu');
  var dugme = document.querySelector('.menu-dugme');
  if (dugme && menu) {
    dugme.addEventListener('click', function () {
      var acik = menu.classList.toggle('acik');
      dugme.setAttribute('aria-expanded', acik ? 'true' : 'false');
      dugme.setAttribute('aria-label', acik ? 'Menüyü kapat' : 'Menüyü aç');
    });
    menu.addEventListener('click', function (e) {
      if (e.target.closest('a')) { menu.classList.remove('acik'); dugme.setAttribute('aria-expanded', 'false'); }
    });
  }
  if (ust) {
    var gol = function () { ust.classList.toggle('kaydi', window.scrollY > 8); };
    gol();
    window.addEventListener('scroll', gol, { passive: true });
  }

  // Giriş: okunan kutular programa sırayla yazılır, toplam artar. Hareket azaltılmışsa hepsi baştan görünür.
  var satirlar = document.querySelectorAll('.program tbody tr');
  var toplam = document.querySelector('[data-toplam]');
  var az = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (satirlar.length && toplam && !az) {
    var tl = function (n) { return n.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' ₺'; };
    var tutar = function (tr) { return parseFloat(tr.lastElementChild.textContent.replace('.', '').replace(',', '.')); };
    satirlar.forEach(function (tr) { tr.hidden = true; });
    toplam.textContent = tl(0);
    var i = 0, sum = 0;
    var yaz = function () {
      if (i >= satirlar.length) return;
      var tr = satirlar[i++];
      tr.hidden = false;
      tr.classList.add('yeni');
      sum += tutar(tr);
      toplam.textContent = tl(sum);
      setTimeout(function () { tr.classList.remove('yeni'); }, 700);
      setTimeout(yaz, 420);
    };
    setTimeout(yaz, 900);
  }

  // İletişim formu: Google Apps Script'e gider (tools/iletisim). Adres yoksa e-posta taslağı açılır.
  var form = document.getElementById('iletisim-formu');
  if (!form) return;
  var durum = form.querySelector('.form-durum');
  var goster = function (tur, metin) { durum.className = 'form-durum ' + tur; durum.textContent = metin; durum.hidden = false; durum.focus(); };
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    if (!form.checkValidity()) { form.reportValidity(); return; }
    var veri = new FormData(form);
    if (veri.get('web')) return; // bal küpü: botlar doldurur
    var adres = form.getAttribute('data-adres');
    if (!adres) {
      var govde = ['Ad soyad: ' + veri.get('ad'), 'Eczane: ' + (veri.get('eczane') || '-'), 'Şehir: ' + (veri.get('sehir') || '-'),
        'Telefon: ' + (veri.get('telefon') || '-'), 'E-posta: ' + veri.get('eposta'), '', veri.get('mesaj')].join('\n');
      window.location.href = 'mailto:destek@eczakod.com?subject=' + encodeURIComponent('EczaKod: ' + veri.get('konu')) + '&body=' + encodeURIComponent(govde);
      goster('tamam', 'E-posta uygulamanız açıldı. Mesajı oradan gönderin; açılmadıysa destek@eczakod.com adresine yazın.');
      return;
    }
    var gonder = form.querySelector('button[type="submit"]');
    gonder.disabled = true;
    gonder.textContent = 'Gönderiliyor…';
    fetch(adres, { method: 'POST', body: new URLSearchParams(veri) })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (!j.ok) throw new Error(j.hata || 'gonderilemedi');
        form.reset();
        goster('tamam', 'Mesajınız bize ulaştı. E-posta adresinize yanıt vereceğiz.');
      })
      .catch(function () {
        goster('hata', 'Mesaj gönderilemedi. İnternet bağlantınızı kontrol edip yeniden deneyin ya da destek@eczakod.com adresine yazın.');
      })
      .finally(function () { gonder.disabled = false; gonder.textContent = 'Mesajı gönder'; });
  });
})();
