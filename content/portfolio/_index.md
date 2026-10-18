+++

title = "Portfolio"
subtitle = "An R package, a data pipeline, and a network-science question about snooker — each written up in full."

# View.
#   1 = List
#   2 = Compact
#   3 = Card
view = 2

# Optional featured image (relative to `static/img/` folder).
[header]
image = ""
caption = ""

# Per-project card metadata, matched to each project by its URL segment
# (`slug` = the last part of the built URL, so `/portfolio/covid_ni/` → "covid_ni").
#   kind    — the mono pill in the card's top-left
#   summary — the card's line of copy (falls back to the project's own summary)
#   links   — the small uppercase row along the card's bottom
# A project with no entry here still renders — it just shows title, summary and date.
[[items]]
slug = "springsteen"
kind = "R package"
summary = "Scraping Brucebase gig data and tidying it into a package you can install from CRAN."
links = [
  { label = "CRAN", url = "https://cran.r-project.org/web/packages/spRingsteen/index.html" },
  { label = "GitHub", url = "https://github.com/obrienjoey/springsteen_db" },
]

[[items]]
slug = "covid_ni"
kind = "Data pipeline"
summary = "Pipelines and dashboards built on Northern Ireland's open COVID-19 data."
links = [
  { label = "GitHub", url = "https://github.com/obrienjoey/covid19northernireland" },
  { label = "Blog post", url = "/post/20220130_covid19ni_data/" },
]

[[items]]
slug = "snooker_rankings"
kind = "Research"
summary = "Ranking snooker careers with network science — the project behind the paper."
links = [
  { label = "Paper", url = "https://academic.oup.com/comnet/article/8/6/cnab003/6161497?login=true" },
  { label = "GitHub", url = "https://github.com/obrienjoey/snooker_rankings" },
]

+++
