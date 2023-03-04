"""
checks the output results.xlsx from leaguer.py
run like
python3 checker.py 2023-02-MensLadies/results-MensLadies-26Apr-9wks-5restdays.xlsx 2023-02-MensLadies/slots.xlsx -r 5

"""
import os
import re
import argparse
from datetime import datetime, timedelta
from collections import Counter
import pandas

parser = argparse.ArgumentParser()
parser.add_argument("fixtures_filename", type=str, help="path to results.xlsx file")
parser.add_argument("-w", "--weeks", type=int, default=8, help="how many weeks from start_date the competition should run for")
parser.add_argument("-r", "--restdays", type=int, default=5,
                    help="the minimum number of days between successive fixtures for any team. "
                        +"1 would mean teams could play a second match the day after a first")
parser.add_argument("-s", "--spread", type=int, default=1, help="allows the weeks of the competition to be spread out, "+
                                                                "eg =2 for interleaving with another competition on alternating weeks")
parser.add_argument("-c", "--csv", action="store_true", help="ingest and output csv files instead of xlsx files")

args = parser.parse_args()


fixtures_filename = args.fixtures_filename
slots_filename    = fixtures_filename.split("/", 1)[0] + "/slots.xlsx"
rest_days         = args.restdays or re.search("(\d+)restdays", fixtures_filename)[1]
date_format       = '%d/%m/%Y'
newline           = "\r\n"

# make fixtures list of dicts with keys: Date,Time,League Type,Event,Draw,Nr,Team 1,Team 2,Court,Location
with open(fixtures_filename, "rb") as xlsxfile:
    fixtures_dataframe = pandas.read_excel(xlsxfile, engine="openpyxl", na_filter=False, dtype={'Date': 'datetime64'})
    fixture_file_headers = fixtures_dataframe.columns
    fixtures = fixtures_dataframe.to_dict(orient="records")
    fixtures = [{k.strip(): v for k, v in fixture.items()} for fixture in fixtures]

with open(slots_filename, "rb") as xlsxfile:
    slots_dataframe = pandas.read_excel(xlsxfile, engine="openpyxl", na_filter=False)
    slots = slots_dataframe.to_dict(orient="records")
    slots = [{k.strip(): v for k, v in slot.items()} for slot in slots]

def get_dates_for_team(fixtures, team):
    home_dates = [x["Date"] for x in fixtures if x["Team 1"] == team]
    away_dates = [x["Date"] for x in fixtures if x["Team 2"] == team]
    return (home_dates, away_dates)

teams = list(set(x["Team 1"] for x in fixtures) & set(x["Team 2"] for x in fixtures))

div_by_team = {x["Team 1"]:x["Event"] for x in fixtures}
div_by_team.update({x["Team 2"]:x["Event"] for x in fixtures})
teams_in_div = Counter(div_by_team.values())

print(teams_in_div)

for team in teams:
    home_dates, away_dates = get_dates_for_team(fixtures, team)
    all_dates = sorted(home_dates + away_dates)
    div = div_by_team[team]
    num_teams = teams_in_div[div]
    home_vs = [x["Team 2"] for x in fixtures if x["Team 1"] == team]
    away_vs = [x["Team 1"] for x in fixtures if x["Team 2"] == team]
    all_vs = home_vs + away_vs

    print(f"{team} to play {len(home_dates) + len(away_dates)} of {num_teams - 1} matches in {div}")
    print(list(x.strftime("%a %d %b") for x in all_dates))
    assert len(home_dates) + len(away_dates) == num_teams - 1, f"{team} doesn't play correct number of matches"
    assert len(set(all_vs)) == num_teams - 1, f"{team} plays a team more than once"
    assert abs(len(home_dates) - len(away_dates)) < 2, f"{team} doesn't play balanced home vs away games"
    assert len(set(x.strftime("%w") for x in home_dates)) == 1, f"{team} doesn't play all home matches on same day of week"
    for i, date in enumerate(all_dates):
        if i == 0: continue
        assert (date - all_dates[i-1] + timedelta(hours=2)).days >= rest_days, f"{team} plays two matches in {rest_days} days"

    slot_buddy = next(iter([x["Team 1"] for x in slots if x["Team 2"] == team] + [x["Team 2"] for x in slots if x["Team 1"] == team]), None)
    if slot_buddy:
        buddy_home_dates, _ = get_dates_for_team(fixtures, slot_buddy)
        assert len(set(buddy_home_dates).intersection(set(home_dates))) == 0, f"{team} plays at home at the same time as a {slot_buddy}"
