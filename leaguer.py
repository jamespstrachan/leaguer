"""
Script to automate time slot allocation to league fixtures, as exported from Tournament Software's
League planner desktop app, ready to be imported to the same.
https://www.tournamentsoftware.com/product/home.aspx?s=6

interactive:
docker run -ti --rm --name leaguer -v "$PWD":/leaguer -w /leaguer python:3.8.0 bash
python leaguer.py

run-once:
docker run -ti --rm --name leaguer -v "$PWD":/leaguer -w /leaguer python:3.8.0-alpine python leaguer.py
"""

import csv
from datetime import datetime, timedelta
import os


rest_days         = 10
output_filename   = 'results {}.csv'.format(datetime.now().strftime('%Y%b%d %H.%M.%S'))
fixtures_filename = 'fixtures.csv'
slots_filename    = 'slots.csv'
date_format       = '%d/%m/%Y'
newline           = "\r\n"
dir_path          = os.path.dirname(os.path.realpath(__file__))

# make fixtures list of dicts with keys: Date,Time,League Type,Event,Draw,Nr,Team 1,Team 2,Court,Location
with open(fixtures_filename, newline=newline) as csvfile:
    reader = csv.DictReader(csvfile, delimiter=',', quotechar='"')
    fixture_file_headers = reader.fieldnames
    fixtures = [x for x in reader]

# make slots list of dicts with keys: Date,Time,Court,Team 1,Team 2
with open(slots_filename, newline=newline) as csvfile:
    reader = csv.DictReader(csvfile, delimiter=',', quotechar='"')
    slots = [x for x in reader]

team_slots = {}
for fixture in fixtures:
    team = fixture['Team 1']
    if team in team_slots:
        continue
    for i, slot in enumerate(slots):
        if team in (slot['Team 1'], slot['Team 2']):
            team_slots[team] = i
            break
    if team not in team_slots:
        raise Exception('Team "{}" have no slot defined in {}'.format(team, slots_filename))

## helps make starting slot for each team
# for team in team_slots.keys():
    # print("7/2/2020,19:00,1,{}".format(team))

divisions = {}
for fixture in fixtures:
    draw = fixture['Draw']
    team = fixture['Team 1']
    if draw not in divisions:
        divisions[draw] = []
    if team not in divisions[draw]:
        divisions[draw].append(team)

# make a copy to work on so we can always refer back to the original
new_fixtures = fixtures


def sort_home_away(team1, team2):
    """ choose the home and away team for the given teams at this point in the schedule
    """
    # if same club, return any
    # if played last year return opposite
    # if team played same club this year, reverse that team's home/away
    # return team with most away matches as home team
    return team1, team2


def date_last_played(team):
    """ returns a date object for the most recent time a team played according to the fixture list
        or last year if they have not yet played
    """
    last_played = datetime.now() - timedelta(weeks=52)
    for fixture in new_fixtures:
        if team in (fixture['Team 1'], fixture['Team 2']) and fixture['Date']:
            last_played = max(last_played, datetime.strptime(fixture['Date'], date_format))
    return last_played


def schedule_fixture(fixtures, team1, team2):
    """ returns an updated fixtures list after scheduling the fixture for the supplied teams as early as
        possible
    """
    for i, fixture in enumerate(fixtures):
        if sorted((team1, team2)) == sorted((fixture['Team 1'], fixture['Team 2'])):
            if fixture['Date']:
                raise Exception('Fixture for {} vs {} already scheduled for {} {}'.format(team1, team2, fixture['Date'], fixture['Time']))

            home_team, away_team  = sort_home_away(team1, team2)
            fixtures[i]['Team 1'] = home_team
            fixtures[i]['Team 2'] = away_team

            slot = slots[team_slots[home_team]]
            match_date = datetime.strptime(slot['Date'], date_format)
            max_date_last_played = max(date_last_played(home_team), date_last_played(away_team))
            while match_date < max_date_last_played + timedelta(days=rest_days):
                match_date = match_date + timedelta(days=7)
            fixtures[i]['Date']   = match_date.strftime(date_format)
            fixtures[i]['Time']   = slot['Time']
            return
    raise Exception('Fixture for {} vs {} is not in the fixtures.py file'.format(team1, team2))

for division, teams in divisions.items():
    print("{} has {} teams:".format(division, len(teams)))
    print(', '.join(teams))

    for i, team in enumerate(teams[0:-1], 1):
        for other_team in teams[i:]:
            if team[0:-2] == other_team[0:-2] and team != other_team:
                print("{} and {} must play early".format(team, other_team))
                schedule_fixture(new_fixtures, team, other_team)

for fixture in new_fixtures:
    if not fixture['Date']:
        schedule_fixture(new_fixtures, fixture['Team 1'], fixture['Team 2'])



#exit()

with open(os.path.join(dir_path, output_filename), 'w', newline='') as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=fixture_file_headers, delimiter=',', quotechar='"')
    writer.writeheader()
    for fixture in fixtures:
        writer.writerow(fixture)
