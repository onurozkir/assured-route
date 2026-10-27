# Simulation context — llm-routing

Yerel doğrulama: 26 Ekim 2026. Resmi Chat Completions sözleşmesinin repodaki
alt kümesinden üretilmiş, sentetik failure handler'ıyla genişletilmiş mock.

## Purpose

Gerçek Assured Route HTTP adapterlarını ucuz/pahalı LLM yerine iki yerel HTTP
üyesine bağlar. Sağlayıcıya ücretli çağrı veya workspace publish yapılmaz.

## Execution

`postman simulation run postman/simulations/llm-routing.sim.yaml --port auto --output ndjson --no-history`
komutunu başlat. `listening.url` adresini al ve başka terminalde
`uv run python demo/check_llm_routing.py --simulation-url <listening-url>` çalıştır.
Çalıştırılan simülasyon sürecini Ctrl+C ile durdur. Logları gitignored
`postman/.runs/` altında tut; request/response değerleri içerebilir.

## Assumptions

- Path routing: iki base URL `<url>/cheap/v1` ve `<url>/expensive/v1` olur;
  `/v1` düşürülürse endpoint eşleşmez (26 Ekim 2026 handler/contract ile doğrulandı).
- Sentetik credential, model ID ve OCR runner içinde sabittir; gerçek key kullanma.
  `interceptRequests: true` body/auth kontrolleri için gereklidir.
- Local mock owner yayını değildir; gerçek model davranışı, kalite, fiyat veya
  sağlayıcıya özgü uyumluluğu kanıtlamaz. Değişiklikte simülasyonu yeniden başlat.

## Observations

<!-- begin:observations -->
26 Ekim 2026: `check_llm_routing.py` 16 senaryoyu geçti. NDJSON logunda
cheap=13, expensive=13 olmak üzere 26 request event'i görüldü; sessiz üye yok.
Cheap kabulde expensive çağrılmadı; fallback'lerde iki üye, semantik verifier'da
expensive üyesi kullanıldı; 1ms bütçede outbound çağrı oluşmadı.
<!-- end:observations -->

## What didn't work

- 26 Ekim 2026: Windows sandbox `~/.postman/` dataset erişimini engelledi;
  simülasyon onaylı sandbox dışı süreçte çalıştırıldı.
- 26 Ekim 2026: create komutu aynı mock'u iki kez eklerken duplicate name üretti;
  üyelerin display adları cheap-llm/expensive-llm olarak ayrıldı, run geçti.
