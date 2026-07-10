from .models import Adjudicacion, Licitacion


def aggregate(scrapers: list) -> list[Licitacion | Adjudicacion]:
    results: list[Licitacion | Adjudicacion] = []
    for scraper in scrapers:
        results.extend(scraper.fetch())
    return results
