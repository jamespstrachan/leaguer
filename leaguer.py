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


rest_days         = 6
output_filename   = 'results {}.csv'.format(datetime.now().strftime('%Y%b%d %H.%M.%S'))
fixtures_filename = 'fixtures.csv'
old_fixtures_filename = 'old_fixtures.csv'
slots_filename    = 'slots.csv'
date_format       = '%d/%m/%Y'
newline           = "\r\n"
dir_path          = os.path.dirname(os.path.realpath(__file__))

# make fixtures list of dicts with keys: Date,Time,League Type,Event,Draw,Nr,Team 1,Team 2,Court,Location
with open(fixtures_filename, newline=newline) as csvfile:
    reader = csv.DictReader(csvfile, delimiter=',', quotechar='"')
    fixture_file_headers = reader.fieldnames
    fixtures = [x for x in reader]

# make old fixtures list of dicts with keys: Date,Time,League Type,Event,Draw,Nr,Team 1,Team 2,Court,Location
with open(old_fixtures_filename, newline=newline) as csvfile:
    reader = csv.DictReader(csvfile, delimiter=',', quotechar='"')
    old_fixtures = [x for x in reader]

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


def is_same_club(team1, team2):
    """ returns true if the club names are identical except for the trailing team number"""
    return team1[0:-2] == team2[0:-2]


def is_same_fixture(team1, team2, fixture):
    """ returns True if the teams are already in the fixture provided """
    return sorted((team1, team2)) == sorted((fixture['Team 1'], fixture['Team 2']))


def sort_home_away(team1, team2):
    """ choose the home and away team for the given teams at this point in the schedule """
    # if same club, return any
    if is_same_club(team1, team2):
        print("   ... same club, home/away doesn't matter")
        return team1, team2

    # if played last year return opposite
    for fixture in old_fixtures:
        if is_same_fixture(team1, team2, fixture):
            print("   ... making {} home team as previous fixture was played at {}".format(fixture['Team 2'], fixture['Team 1']))
            return fixture['Team 2'], fixture['Team 1']

    # if either team played same club already this league, reverse that team's home/away
    for fixture in fixtures:
        if not fixture['Date']:
            continue
        if fixture['Team 1'] == team1 and is_same_club(team2, fixture['Team 2']):
            print('   ... {} already hosted {}, making them play {} away'.format(team1, fixture['Team 2'], team2))
            return team2, team1
        if fixture['Team 2'] == team1 and is_same_club(team2, fixture['Team 1']):
            print('   ... {} already played away against {}, making them play {} at home'.format(team1, fixture['Team 1'], team2))
            return team1, team2
        if fixture['Team 1'] == team2 and is_same_club(team1, fixture['Team 2']):
            print('   ... {} already hosted {}, making them play {} away'.format(team2, fixture['Team 2'], team1))
            return team1, team2
        if fixture['Team 2'] == team2 and is_same_club(team1, fixture['Team 1']):
            print('   ... {} already played away against {}, making them play {} at home'.format(team2, fixture['Team 1'], team1))
            return team2, team1

    # return team with most away matches as home team
    return team1, team2


def date_team_last_played(team):
    """ returns a date object for the most recent time a team played according to the fixture list
        or last year if they have not yet played
    """
    last_played = datetime.now() - timedelta(weeks=52)
    for fixture in fixtures:
        if team in (fixture['Team 1'], fixture['Team 2']) and fixture['Date']:
            last_played = max(last_played, datetime.strptime(fixture['Date'], date_format))
    return last_played


def can_team_play_at_home_on_date(home_team, away_team, date):
    """ returns True if the team doesn's share its slot with another team.
        returns True if the shared slot isn't booked on that date by the sharing_team, or if the
        away_team is the sharing_team
    """
    sharing_team = slots[team_slots[home_team]]['Team 2']
    if sharing_team == home_team:
        sharing_team = slots[team_slots[home_team]]['Team 1']

    if sharing_team and sharing_team != away_team: # if the sharing_team is the away_team that's fine!
        for fixture in fixtures:
            if fixture['Date'] == date.strftime(date_format) and fixture['Team 1'] == sharing_team:
                print('   ... {} are using the slot shared with {} on {}'.format(sharing_team, home_team, date.strftime(date_format)))
                return False
    return True



def schedule_fixture(fixtures, team1, team2):
    """ returns an updated fixtures list after scheduling the fixture for the supplied teams as early as
        possible
    """
    for i, fixture in enumerate(fixtures):
        if is_same_fixture(team1, team2, fixture):
            if fixture['Date']:
                raise Exception(' ! Fixture for {} vs {} already scheduled for {} {}'.format(team1, team2, fixture['Date'], fixture['Time']))

            home_team, away_team  = sort_home_away(team1, team2)
            fixtures[i]['Team 1'] = home_team
            fixtures[i]['Team 2'] = away_team

            slot             = slots[team_slots[home_team]]
            date_proposed    = datetime.strptime(slot['Date'], date_format)
            date_last_played = max(date_team_last_played(home_team), date_team_last_played(away_team))
            while date_proposed < date_last_played + timedelta(days=rest_days) \
                  or not can_team_play_at_home_on_date(home_team, away_team, date_proposed):
                date_proposed = date_proposed + timedelta(days=7)

            fixtures[i]['Date'] = date_proposed.strftime(date_format)
            fixtures[i]['Time'] = slot['Time']
            print("   ... scheduled for {} on {} at {}".format(fixtures[i]['Time'], fixtures[i]['Date'], home_team))
            return
    raise Exception(' ! Fixture for {} vs {} is not in the fixtures.py file'.format(team1, team2))


for division, teams in divisions.items():
    print("==========================================================================")
    print(" {} has {} teams:".format(division, len(teams)))
    print(' '+', '.join(teams))
    print("==========================================================================")

    for i, team in enumerate(teams[0:-1], 1):
        for other_team in teams[i:]:
            if is_same_club(team, other_team) and team != other_team:
                print(" ! {} and {} must play early".format(team, other_team))
                schedule_fixture(fixtures, team, other_team)

    for fixture in fixtures:
        if fixture['Draw'] == division and not fixture['Date']:
            print(" + scheduling {} vs {} ...".format(fixture['Team 1'], fixture['Team 2']))
            schedule_fixture(fixtures, fixture['Team 1'], fixture['Team 2'])

# Sort the fixture list by division then by match date, time
fixtures = sorted(fixtures, key=lambda row: (row['Draw'], datetime.strptime(row['Date'], date_format), row['Time']))

team_stats = {}
for fixture in fixtures:
    for column_heading in ('Team 1', 'Team 2'):
        team = fixture[column_heading]
        if team not in team_stats:
            team_stats[team] = {
                'home_matches': 0,
                'away_matches': 0,
                'match_dates': [],
            }
        team_stats[team]['match_dates'].append(datetime.strptime(fixture['Date'], date_format))
        if column_heading == 'Team 1':
            team_stats[team]['home_matches'] += 1
        else:
            team_stats[team]['away_matches'] += 1

print("==========================================================================")
print(' Summary  -  minimum {} days rest'.format(rest_days))
print("==========================================================================")
name_pad_len  = max(len(x) for x in team_stats.keys())
first_fixture = datetime.now() + timedelta(weeks=52)
last_fixture  = datetime.now() - timedelta(weeks=52)
for team, stats in team_stats.items():
    dates = sorted(stats['match_dates'])
    first_fixture = min(first_fixture, min(dates))
    last_fixture  = max(last_fixture, max(dates))
    days_rest = [(date-dates[i]).days for  i, date in enumerate(dates[1:])]
    print(' {:<{name_pad_len}} : {}h/{}a  rest for {} to {} days'.format(
        team,
        stats['home_matches'],
        stats['away_matches'],
        min(days_rest),
        max(days_rest),
        name_pad_len=name_pad_len))

print("")
print(' runs from {} to {}'.format(first_fixture.strftime(date_format), last_fixture.strftime(date_format)))
print("==========================================================================")


with open(os.path.join(dir_path, output_filename), 'w', newline='') as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=fixture_file_headers, delimiter=',', quotechar='"')
    writer.writeheader()
    for fixture in fixtures:
        writer.writerow(fixture)
