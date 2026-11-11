# Daily rates for the நாட்காட்டி app

`rates.json` here is what the app shows as today's gold, silver, USD and fuel prices.
A free GitHub Actions job updates it three times a day; GitHub Pages serves it.

## One-time setup (about 10 minutes)

1. Create a **public** GitHub repository, e.g. `tamil-calendar-data`, and push this folder to it.
2. Repository → Settings → Pages → Source: *Deploy from a branch*, branch `main`, folder `/ (root)`.
3. Repository → Actions → enable workflows; open *update-rates* → **Run workflow** once.
4. The file is now at `https://<your-user>.github.io/tamil-calendar-data/rates.json`.
   Build the app with that URL:
   `./gradlew assembleRelease -PratesUrl=https://<your-user>.github.io/tamil-calendar-data/rates.json`
   (or put `ratesUrl=...` in `~/.gradle/gradle.properties`).

## When petrol/diesel prices change

Edit `fuel.json` (on github.com: open the file → ✏️ → change the numbers and `checked` date → Commit).
The next run publishes it. Oil companies' sites block automated reading, so this is manual;
prices change only a few times a year.

## Notes

- Gold/silver: IBJA benchmark rates, **excluding GST and making charges**; jewellery shop
  board rates in Chennai differ slightly. IBJA does not publish on holidays/weekends — the
  last published rate stays.
- USD: open.er-api.com (free, updated daily) — the app shows "Rates By Exchange Rate API".
- If a source fails, the previous values are kept and an `errors` field is added.
- GitHub disables scheduled workflows in repos with no activity for 60 days; the bot's own
  commits count as activity, but if it ever stops, open Actions and re-enable it.
