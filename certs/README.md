# Сертификаты НУЦ Минцифры

`ticket.rzd.ru` работает на сертификате Национального удостоверяющего центра
Минцифры России. Обращения к API оттуда падают с
`SSLCertVerificationError: unable to get local issuer certificate` по двум
независимым причинам:

1. корня `Russian Trusted Root CA` нет ни в `certifi` (его по умолчанию
   использует `requests`), ни в системном store Debian/Ubuntu;
2. листовой сертификат подписан промежуточным `Russian Trusted Sub CA`, но
   сервер его в TLS-хендшейке **не отдаёт** — вместо него присылает сам корень.
   Поэтому одного корня недостаточно, цепочку без промежуточного не построить.

`russian_trusted.pem` содержит оба сертификата и подставляется в `verify=`
через `config.rzd_verify()` во всех запросах к РЖД
(`services/rzd_api.py`, `services/rzd_seatmap.py`).

## Что внутри

| Сертификат | Действует до | Откуда взят |
|---|---|---|
| Russian Trusted Root CA | 27.02.2032 | TLS-цепочка `ticket.rzd.ru` |
| Russian Trusted Sub CA  | 19.07.2029 | `http://nuc-cdp.digital.gov.ru/cdp/subca_ssl_rsa2024.crt` (AIA листового сертификата) |

Официальные зеркала: `https://gu-st.ru/content/lp/russian-trusted-root-ca.cer`,
`http://nuc-cdp.voskhod.ru/cdp/`.

## Как обновить

Актуальный адрес промежуточного всегда лежит в самом сертификате сайта:

```bash
openssl s_client -connect ticket.rzd.ru:443 -servername ticket.rzd.ru </dev/null 2>/dev/null \
  | openssl x509 -noout -ext authorityInfoAccess
```

Скачать по указанному там `CA Issuers` URI и склеить с корнем в один PEM.
Проверка, что бандл рабочий:

```bash
curl --cacert certs/russian_trusted.pem "https://ticket.rzd.ru/api/v1/suggests?Query=Москва"
```

## Отключить

`RZD_CA_BUNDLE=` (пустое значение) в `.env` вернёт обычную проверку по `certifi` —
на случай, если РЖД когда-нибудь переедет обратно на публичный CA.
