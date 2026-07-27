# rejstrik-mcp

[![CI](https://github.com/janF19/rejstrik-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/janF19/rejstrik-mcp/actions/workflows/ci.yml) [![PyPI](https://img.shields.io/pypi/v/rejstrik-mcp)](https://pypi.org/project/rejstrik-mcp/)

**Připojte český obchodní rejstřík ke svému Claude za 30 sekund — bez
jakéhokoli API klíče. Účetní závěrky ze Sbírky listin čte váš vlastní
model v rámci vašeho předplatného.**

![Ukázka: Claude najde firmu, přečte její účetní závěrku a spočítá finanční poměrové ukazatele](docs/media/robe-analyze.gif)

```bash
claude mcp add rejstrik -- uvx rejstrik-mcp
```

*(English note: this is an MCP server for the Czech business registry;
the README is in Czech because that's who the data serves. Tool names and
descriptions inside the server are in English.)*

## Co to umí

- **Vyhledání firmy** podle názvu nebo IČO (ARES) včetně statutárních
  orgánů a CZ-NACE.
- **Sbírka listin:** výpis dokumentů a stažení skutečně podaných PDF
  účetních závěrek (nejnovější, podle roku, nebo podle id) — včetně
  textové vrstvy po stránkách a PNG náhledů u skenů.
- **Finanční analýza bez LLM na serveru:** váš agent přečte PDF sám,
  vytěžené hodnoty pošle zpět a server deterministicky spočítá poměrové
  ukazatele, bankrotní index IN05, meziroční trendy a red flags.
- **Orientační ocenění** (účetní hodnota, kapitalizované zisky, oborové
  násobky EV/EBITDA dle Damodarana). Není investiční doporučení.
- **Prověrky:** insolvenční rejstřík (ISIR), spolehlivost plátce DPH
  (ADIS), státní dotace (IS ReD), smlouvy z Registru smluv.
- **Report card:** shrnutí jako přehledný markdown (výchozí, funguje
  všude — Claude Code, Desktop, …). Interaktivní HTML karta je
  implementovaná dle MCP Apps (SEP-1865), ale klienti ji zatím
  nevykreslují (upstream [ext-apps#671](https://github.com/modelcontextprotocol/ext-apps/issues/671)),
  takže se automaticky použije markdown.

Žádná OCR pipeline, žádná vektorová databáze, žádný serverový AI klíč —
čtení dokumentů dělá model, kterým se ptáte.

## Ukázkové prompty

Po instalaci se stačí Clauda zeptat česky (nebo jakkoli jinak):

> **„Analyzuj hospodaření firmy ISOTRA a.s. za poslední 2 roky."**

Agent najde IČO přes ARES, stáhne podané závěrky ze Sbírky listin, sám je
přečte a od serveru dostane spočítanou analýzu. Typický výsledek:

| Ukazatel | 2024 | 2023 | Změna |
|---|---|---|---|
| Tržby | 1 490 957 | 1 437 917 | +3,7 % |
| Provozní VH (EBIT) | 87 166 | 82 764 | +5,3 % |
| Čistý zisk | 60 074 | 54 631 | +10,0 % |
| Vlastní kapitál | 366 214 | 326 140 | +12,3 % |

*(v tis. Kč)* … plus poměrové ukazatele (běžná likvidita 1,73; ROE
16,4 %; úrokové krytí 13,4×), **IN05: 1,80 — pásmo tvorby hodnoty**,
žádné red flags, citace stránek u klíčových čísel.

> **„Prověř firmu Budějovický Budvar — insolvence, DPH, kdo ji řídí,
> dotace a veřejné zakázky."**

Vrátí stav v ISIR, registraci a spolehlivost plátce DPH, statutární
orgány, přehled přijatých dotací a smluv z Registru smluv.

> **„Odhadni orientační hodnotu firmy XYZ s.r.o."**

Vrátí bodový odhad hodnoty s pásmem spolehlivosti, použitý násobek
(základ z Damodaran Europe + jmenované korekce) a upozornění, že nejde o
investiční doporučení.

> **Vestavěný prompt `analyze-company`** (v Claude se nabízí jako slash
> příkaz) provede celou smyčku najednou: najít → stáhnout PDF → vytěžit →
> analyzovat → karta, včetně víceletých trendů.

Skutečný bezklíčový přepis session je v
[`docs/media/cli-demo.txt`](docs/media/cli-demo.txt) — vyhledání firmy
přes ARES a výpis podaných závěrek přímo ze Sbírky listin, bez
nastaveného jakéhokoli API klíče.

## Proč právě tento

|  | agent-native (MCP) | čte podaná PDF | zdarma & open source | funguje bez API klíče |
|---|---|---|---|---|
| cz-agents-mcp a podobné | ✅ | ❌ | ✅ | ✅ |
| chytryrejstrik.cz | ❌ | částečně (placené) | ❌ | — |
| **rejstrik-mcp** | ✅ | ✅ | ✅ | ✅ |

## Instalace

**Claude Code:** `claude mcp add rejstrik -- uvx rejstrik-mcp`

**Claude Desktop:** stáhněte `rejstrik-mcp.mcpb` z nejnovější GitHub
release a poklepejte na něj (vyžaduje [uv](https://docs.astral.sh/uv/)) —
nebo přidejte do `claude_desktop_config.json`:

```json
{ "mcpServers": { "rejstrik": { "command": "uvx", "args": ["rejstrik-mcp"] } } }
```

**Codex** (`~/.codex/config.toml`):

```toml
[mcp_servers.rejstrik]
command = "uvx"
args = ["rejstrik-mcp"]
```

**Libovolný HTTP host:** `uvx rejstrik-mcp --http` servíruje streamable
HTTP na `http://127.0.0.1:8000/mcp`.

## Nástroje

Čtení dělá váš agent v rámci vašeho předplatného; server dělá vše
deterministické:

| Nástroj | Co dělá |
|---|---|
| `find_company` | Najde firmu podle názvu nebo IČO (ARES) |
| `list_filings` | Vypíše dokumenty ze Sbírky listin, účetní závěrky první |
| `get_filing` | Stáhne PDF závěrky (nejnovější, dle roku, dle id) — vrací lokální cestu + `page_count`; `embed` řídí, zda se vrátí i bajty PDF (`"auto"` výchozí, `"always"`, `"never"`) |
| `read_filing_text` | Textová vrstva PDF po stránkách, bez LLM/OCR; stránky bez textové vrstvy poctivě ohlásí |
| `read_filing_page_images` | Stránky PDF jako PNG obrázky — pro skenované závěrky bez textové vrstvy |
| `analyze_financials` | Vaše vytěžené hodnoty → poměrové ukazatele, red flags, index IN05, meziroční trendy (bez LLM) |
| `estimate_valuation` | Vaše vytěžené hodnoty → orientační hodnota firmy: sektorový násobek EV/EBITDA (Damodaran Europe) upravený na český soukromý podnik, bodový odhad s pásmem spolehlivosti a výpisem všech korekcí. Bez LLM. Není investiční doporučení |
| `render_card` | Report jako karta — interaktivní HTML pro hosty s MCP Apps, markdown pro textové hosty jako Claude Code |
| `check_insolvency` | Insolvenční rejstřík (ISIR) |
| `get_statutory_bodies` | Statutární orgány (ARES) |
| `check_vat` | Registrace k DPH + příznak nespolehlivého plátce (ARES + ADIS) |
| `get_subsidies` | Přijaté státní dotace (IS ReD, dříve CEDR) |
| `get_contracts` | Smlouvy firmy z Registru smluv |

**Skuteční majitelé.** Veřejná část ESM (Evidence skutečných majitelů)
byla po rozsudku Soudního dvora EU k 17. 12. 2025 uzavřena; dotazy na
skutečné majitele proto záměrně nenabízíme — jde o zdokumentované
rozhodnutí o rozsahu, ne o mezeru.

## Jak to funguje

```text
core/      sdílené HTTP + textové utility
registry/  ARES, ISIR (insolvence), ADIS (DPH), statutární orgány
filings/   klient Sbírky listin (verejnerejstriky.msp.gov.cz,
           s fallbackem na starší or.justice.cz při blokaci)
documents/ stažení a cache PDF + extrakce textu / obrázků stránek
analysis/  normalizace -> ukazatele -> red flags -> trendy (čisté, bez I/O)
service/   orchestrace (rejstříky + listiny + dokumenty + analýza)
cli/ mcp/  dvě tváře nad jedním jádrem
```

Server je zcela **bezklíčový**: dokumenty čte volající model (Claude
apod.), server dodává data a deterministické výpočty. Vytěžená data se
předávají přes Pydantic schéma `FinancialStatement` — vestavěný prompt
`analyze-company` agenta instruuje, jak čísla přepisovat doslova včetně
deklarovaného měřítka („v celých tisících Kč“).

### Poznámka k driftu reálného světa

V průběhu vývoje Ministerstvo spravedlnosti migrovalo Sbírku listin z
`or.justice.cz` na nový portál (`verejnerejstriky.msp.gov.cz`). Klient
míří na API nového portálu. V červenci 2026 začal nový portál vracet
automatizovaným klientům blokace Azure Front Door (403/429/5xx i 200 s
challenge HTML) — klient je všechny detekuje jako blokaci a přepadne na
starší portál, takže jediná zablokovaná edge lokalita nevyřadí vyhledávání.
Kanárek v `scripts/smoke.py` testuje oba portály přímo a hlásí
PASS/BLOCKED po endpointech, takže se drift odhalí před vydáním, ne u
uživatelů.

### Data oborových násobků pro ocenění

`src/rejstrik/analysis/data/industry_multiples.json` vendoruje oborové
EV/EBITDA násobky **Damodaran Europe** (zdroj, source_url, as_of i region
jsou v souboru). NACE slouží jen jako mapovací klíč do Damodaranovy
taxonomie — žádné ručně laděné násobky. Regenerace (síť, manuálně, nikdy
v CI):

    pip install xlrd
    python scripts/import_damodaran_multiples.py --as-of YYYY-MM-DD

## CI

Workflow v `.github/workflows/ci.yml` pouští `ruff` a `pytest` na Pythonu
3.11 a 3.12. Testy jsou záměrně offline a bez klíčů — zelené CI znamená,
že fixtures, parsery, servisní vrstva, CLI i MCP registrace jsou vnitřně
konzistentní bez závislosti na dostupnosti živých endpointů.

## Vývoj

```bash
pip install -e ".[dev]"
ruff check src/ tests/
ruff format --check src/ tests/
python -m pytest -q
```

Užitečné ruční smoke testy:

```bash
rejstrik find "Budejovicky Budvar"
rejstrik filings 00514152
rejstrik-mcp
python scripts/smoke.py   # vyžaduje síť — před vydáním, ne v CI
```

## Poděkování / attribution

Klienti pro insolvenci (ISIR), DPH/nespolehlivé plátce (ADIS) a
statutární orgány jsou adaptovaní z
[cz-agents-mcp](https://github.com/martinhavel/cz-agents-mcp) (MIT,
Martin Havel). Viz `LICENSES/cz-agents-mcp-LICENSE`.

## Vydávání

1. Jednorázově: na pypi.org přidejte *Trusted Publisher* pro tento GitHub
   repozitář (workflow `release.yml`, environment `pypi`).
2. Zvedněte `version` na **všech čtyřech** místech, aby souhlasila:
   `pyproject.toml`, `server.json` (top-level **i** `packages[0].version`),
   `mcpb/manifest.json` a `src/rejstrik/__init__.py` (`__version__`).
   `tests/test_version_sync.py` selže, pokud se rozjedou.
3. Pokud vydání mění publikovaný server, znovu proveďte publish do MCP
   registru s aktualizovaným `server.json`.
4. Commit, tag `vX.Y.Z`, push tagu. CI sestaví balíček, publikuje na PyPI
   a připojí artefakty ke GitHub release.

## Licence

MIT.
