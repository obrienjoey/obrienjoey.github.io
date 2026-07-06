---
title: COVID Northern Ireland
author: ''
date: '2022-02-22'
slug: []
categories: []
tags: []
subtitle: ''
summary: 'Creating data pipelines and dashboard visualizations from the COVID-19 Pandemic in Northern Ireland.'
authors: []
lastmod: '2022-02-22T22:02:41Z'
featured: no
image:
  caption: ''
  focal_point: ''
  preview_only: no
projects: []
---

One of the many scientific benefits that have occurred since the start of the Coronavirus 19 pandemic is the emergence of large-scale open access data describing the dynamics of the virus at a range of scales. Governments, health organizations, and many others have produced data at a unparalleled rate to help society understand how the disease has rampaged through society. 

This has offered a unique opportunity for data analysts, engineers, scientists, or even simply enthusiasts, to work with real world data that is constantly evolving as the pandemic unfolds. There are great examples of storytelling that have emerged from this occurrence, for example the _flatten the curve_ narrative which was so prevalent in the early stages all the way up to more recent information regarding vaccination uptake globally. 

I myself have been fortunate to have been involved in numerous efforts in utilizing these novel datasets, for example early data studies regarding mobility data (provided by Apple and Google) among citizens in Ireland were a particular entertaining aspect for me as virus begun to spread, see for example this [invited blog post](https://ecmiindmath.org/2020/07/01/covid-19-and-the-irish-routine/) on Irish mobility) or some [visuals]([https://twitter.com/obrienj_/status/1253248715940380677]) which picked up national attention.

More recently I have focused on the affect of the pandemic in Northern Ireland. The work on which will be the main discussion point of this post.

### Data Collection

Firstly, like any good data scientist I had to ask the question - where is the data? It turns out that the [Department of Health NI](https://www.health-ni.gov.uk/publications/daily-dashboard-updates-covid-19-november-2021) produce a fantastic summary of the main metrics describing the disease including, cases, testing, hospitilizations, and deaths arising from Covid-19 on a daily-ish basis (more on this in a moment). Unfortunately, for those of us who want to access data as quickly and cleanly as possible, the data is stored in rather clunky _.xlsx_ spreadsheets with each tab representing a different summary. 

1. Look for the latest spreadsheet on a daily basis.
2. Extract the needed info from each of the sheets of the .xlsx file individually.
3. Clean this data in a more usable format.
4. Store the data in a public repository for others to use.

This is exactly the framework introduced in the [**covid19northernireland**](https://github.com/obrienjoey/covid19northernireland) repo hosted on my GitHub. The main point of this code is to first of all collect the latest spreadsheet from the online platform, clean and parse the data into a tidy format, and lastly store the data. Nicely, due to the repetitive nature of this task I could set up a server which would do this for me automatically each night and produce the output observed in the repo. See [this post](https://www.joeyobrien.ie/post/20220130_covid19ni_data/) for a detailed discussion on how this entire package works.

### Dashboard

Okay, so the data has been collected in a great format which is very easy to work with. Of course there are a huge number of things one could do here (epidemic modelling, spatial statistics,...) but I really wanted to learn about developing dashboards in `R` so that's what I'll write about now (to see the finished product check [**here**](https://obrienjoey.github.io/covidni_dashboard/)). 

After some initial research I came across the [`flexdashboard`](https://rstudio.github.io/flexdashboard/index.html) package which looked to be perfect for what I wanted to do. In essence it is entirely described in a `.Rmarkdown` document so it is generally okay to work with, plus can look quite fantastic if given a bit of love and care (and help from the `plotly` package!), for example here's one page of the finished dashboard.   

![The Covid19 Northern Ireland Dashboard](covid_ni_dashboard.PNG)

For some more specifics about how it works, it makes use of a number of the cleaned datasets from the first part of this post to extract information about tests, cases, and deaths at an number of time and spatial scales. For example it was possible to load in the data at an electoral level to see how the number of cases varied by region using the `mapview` package:


``` r
`%>%` <- magrittr::`%>%`
### Pulling most recent data from Github
national_df <- data.table::fread("https://raw.githubusercontent.com/obrienjoey/covid19northernireland/main/data/ni_covid_national.csv")
last_national_data <- national_df %>%
                        tidyr::drop_na() %>% 
                        dplyr::filter(date == max(date))

local_df <- data.table::fread("https://raw.githubusercontent.com/obrienjoey/covid19northernireland/main/data/ni_covid_local.csv")

shapefile <- sf::st_read(
  "shapefiles/OSNI_Open_Data_-_Largescale_Boundaries_-_Local_Government_Districts_(2012).shp", quiet = TRUE)

local_df_summary <- local_df %>%
              dplyr::distinct() %>%
              dplyr::mutate_if(is.numeric, ~replace(., is.na(.), 0)) %>%
              dplyr::group_by(area) %>%
              dplyr::summarise(tests_1 = sum(tail(tests,1)),
                               tests_7 = sum(tail(tests,7)),
                               tests_30 = sum(tail(tests,30)),
                               tests_all = sum(tests),
                               cases_1 = sum(tail(cases,1)),
                               cases_7 = sum(tail(cases,7)),
                               cases_30 = sum(tail(cases,30)),
                               cases_all = sum(cases),
                               deaths_1 = sum(tail(deaths,1)),
                               deaths_7 = sum(tail(deaths,7)),
                               deaths_30 = sum(tail(deaths,30)),
                               deaths_all = sum(deaths)) %>%
              janitor::adorn_totals("row") %>%
              dplyr::as_tibble() %>%
              dplyr::filter(area != 'Missing Postcode') %>%
              tidyr::drop_na() %>%
              tidyr::pivot_longer(cols = tests_1:deaths_all,
                           names_to = 'category') %>%
              tidyr::separate(category, 
                       into = c("Category", "Time"),
                       sep="_(?=[^_]+$)")

map_df <- local_df_summary %>%
  dplyr::filter(Time == 1,
                Category == 'cases') %>%
  dplyr::inner_join(shapefile, .,
                    by = c('LGDNAME' = 'area'))

mapview::mapview(sf::st_zm(map_df), 
                 zcol = c('value'),
                 layer.name = 'Cases',
                 popup = FALSE)
```

![The Covid19 Northern Ireland Dashboard](map.PNG)

The main problem then was that the underlying of this data updates daily as discussed before. However given the data pipeline is already set up, a similar server can be utilized to automatically update the dashboard after the original collection script has run. 

### Conclusions

So there we have it, a discussion on developing a pipeline to automatically update and collect data (which I had a lot of fun doing, maybe I should think about a career in data engineering...) and also creating a number of visualizations to create a story regarding the pandemic's evolution. Wrapping these altogether in a neat [dashboard](https://obrienjoey.github.io/covidni_dashboard/) which I particularly like! 
