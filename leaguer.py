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
import pandas
from datetime import datetime, timedelta
import os

file_format       = 'xlsx'
# file_format      = 'csv'
rest_days         = 4
output_filename   = 'results {}.{}'.format(datetime.now().strftime('%Y%b%d %H.%M.%S'), file_format)
fixtures_filename = 'fixtures.{}'.format(file_format)
old_fixtures_filename = 'old_fixtures.{}'.format(file_format)
slots_filename    = 'slots.{}'.format(file_format)
date_format       = '%d/%m/%Y'
newline           = "\r\n"
dir_path          = os.path.dirname(os.path.realpath(__file__))
league_start_date = datetime.strptime('24/04/2020', date_format)
league_end_date   = datetime.strptime('28/06/2020', date_format)

if file_format == 'xlsx':
    # make fixtures list of dicts with keys: Date,Time,League Type,Event,Draw,Nr,Team 1,Team 2,Court,Location
    with open(fixtures_filename, "rb") as xlsxfile:
        fixtures_dataframe = pandas.read_excel(xlsxfile, engine="openpyxl", na_filter=False)
        fixture_file_headers = fixtures_dataframe.columns
        fixtures = fixtures_dataframe.to_dict(orient="records")

    # make old fixtures list of dicts with keys: Date,Time,League Type,Event,Draw,Nr,Team 1,Team 2,Court,Location
    with open(old_fixtures_filename, "rb") as xlsxfile:
        old_fixtures_dataframe = pandas.read_excel(xlsxfile, engine="openpyxl", na_filter=False)
        old_fixtures = old_fixtures_dataframe.to_dict(orient="records")

    # make slots list of dicts with keys: Date,Time,Court,Team 1,Team 2
    with open(slots_filename, "rb") as xlsxfile:
        slots_dataframe = pandas.read_excel(xlsxfile, engine="openpyxl", na_filter=False)
        slots = slots_dataframe.to_dict(orient="records")

else:
    # make fixtures list of dicts with keys: Date,Time,League Type,Event,Draw,Nr,Team 1,Team 2,Court,Location
    with open(fixtures_filename, newline=newline) as csvfile:
        reader = csv.DictReader(csvfile, delimiter=',', quotechar='"')
        fixture_file_headers = reader.fieldnames
        fixtures = list(reader)

    # make old fixtures list of dicts with keys: Date,Time,League Type,Event,Draw,Nr,Team 1,Team 2,Court,Location
    with open(old_fixtures_filename, newline=newline) as csvfile:
        reader = csv.DictReader(csvfile, delimiter=',', quotechar='"')
        old_fixtures = list(reader)

    # make slots list of dicts with keys: Date,Time,Court,Team 1,Team 2
    with open(slots_filename, newline=newline) as csvfile:
        reader = csv.DictReader(csvfile, delimiter=',', quotechar='"')
        slots = list(reader)


fixtures = [x for x in fixtures if x['Team 1'] != 'Bye']


team_slots = {}
teams_sharing_slots = []
for fixture in fixtures:
    team = fixture['Team 1']
    if team in team_slots:
        continue
    for i, slot in enumerate(slots):
        if team in (slot['Team 1'], slot['Team 2']):
            if slot['Team 2']:
                teams_sharing_slots.append(slot['Team 1'])
                teams_sharing_slots.append(slot['Team 2'])
            team_slots[team] = i
            break
    if team not in team_slots:
        raise Exception('Team "{}" have no slot defined in {}'.format(team, slots_filename))

fixtures_scheduled = [{'team': team,
                       'fixtures': 0,
                       'next_date': datetime.strptime(slots[slot_idx]['Date'], date_format),
                       }
                      for team, slot_idx in team_slots.items()]

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


def is_fixture_scheduled(team1, team2):
    """ returns True if the teams are already scheduled to play """
    for fixture in fixtures:
        if fixture['Date'] and is_same_fixture(team1, team2, fixture):
            return True
    return False


def sort_home_away(team1, team2):
    """ choose the home and away team for the given teams at this point in the schedule """
    # if same club, return any
    if is_same_club(team1, team2):
        print("    same club, home/away doesn't matter")
        return team1, team2

    date_team1 = date_of_next_home_slot(team1)
    date_team2 = date_of_next_home_slot(team2)
    lose_home_advantage_after_days = 10
    if abs((date_team1 - date_team2).days) > lose_home_advantage_after_days:
        if date_team1 > date_team2:
            print("    {} can't do home for + {} days longer than {}".format(team1, lose_home_advantage_after_days, team2))
            return team2, team1
        else:
            print("    {} can't do home for + {} days longer than {}".format(team2, lose_home_advantage_after_days, team1))
            return team1, team2

    team1_away, team1_home, team2_away, team2_home = 0,0,0,0
    # if either team played same club already this league, reverse that team's home/away
    for fixture in fixtures:
        if not fixture['Date']:
            continue
        if team1 == fixture['Team 1']:
            team1_home += 1
            if is_same_club(team2, fixture['Team 2']):
                print('    {} already hosted {}, making them play {} away'.format(team1, fixture['Team 2'], team2))
                return team2, team1
        if team1 == fixture['Team 2']:
            # Don't count matches as 'away' if they were played against a team from same club
            if is_same_club(team1, fixture['Team 1']):
                team1_home += 1
            else:
                team1_away += 1

            if is_same_club(team2, fixture['Team 1']):
                print('    {} already played away against {}, making them play {} at home'.format(team1, fixture['Team 1'], team2))
                return team1, team2
        if team2 == fixture['Team 1']:
            team2_home += 1
            if is_same_club(team1, fixture['Team 2']):
                print('    {} already hosted {}, making them play {} away'.format(team2, fixture['Team 2'], team1))
                return team1, team2
        if team2 == fixture['Team 2']:
            # Don't count matches as 'away' if they were played against a team from same club
            if is_same_club(team2, fixture['Team 1']):
                team2_home += 1
            else:
                team2_away += 1

            if is_same_club(team1, fixture['Team 1']):
                print('    {} already played away against {}, making them play {} at home'.format(team2, fixture['Team 1'], team1))
                return team2, team1

    # if played last year return opposite
    for fixture in old_fixtures:
        if is_same_fixture(team1, team2, fixture):
            print("    making {} home team as previous fixture was played at {}".format(fixture['Team 2'], fixture['Team 1']))
            return fixture['Team 2'], fixture['Team 1']

    # correct the team with the most different home vs away count
    # teams who share a slot are slightly penalised to bias towards having one more away game than home game
    team1_shared_slot_penalty = 1 if team1 in teams_sharing_slots else 0
    team2_shared_slot_penalty = 1 if team2 in teams_sharing_slots else 0
    msg = '   ... {} have scheduled {}h+{}/{}a, {} have scheduled {}h+{}/{}a'
    print(msg.format(team1, team1_home, team1_shared_slot_penalty, team1_away,
                     team2, team2_home, team2_shared_slot_penalty, team2_away)  )

    team1_home_away_diff = abs(team1_home + team1_shared_slot_penalty - team1_away)
    team2_home_away_diff = abs(team2_home + team2_shared_slot_penalty - team2_away)
    if team1_home_away_diff > team2_home_away_diff: # correct the most different team
        if team1_home < team1_away:
            return team1, team2
        return team2, team1
    else:
        if team2_home < team2_away:
            return team2, team1
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


def date_of_next_home_slot(team, after_date=None):
    """ returns a date object for the team's next empty home slot
    """
    date_last_played = date_team_last_played(team)
    date_proposed = datetime.strptime(slots[team_slots[team]]['Date'], date_format)
    after_date = after_date or date_last_played + rest_delta

    while date_proposed < after_date \
          or not can_team_play_at_home_on_date(team, 'ANY', date_proposed):
        date_proposed = date_proposed + timedelta(days=7)

    return date_proposed


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


rest_delta = timedelta(days=rest_days)

def schedule_fixture(fixtures, team1, team2):
    """ returns an updated fixtures list after scheduling the fixture for the supplied teams as early as
        possible
    """
    team1_date_last_played = date_team_last_played(team1)
    team2_date_last_played = date_team_last_played(team2)
    print("    {} last played {}, {} last played {}".format(team1, team1_date_last_played.strftime(date_format), team2, team2_date_last_played.strftime(date_format)))

    home_team, away_team  = sort_home_away(team1, team2)
    after_date = max(team1_date_last_played, team2_date_last_played) + rest_delta
    date_proposed = date_of_next_home_slot(home_team, after_date)

    for i, fixture in enumerate(fixtures):
        if is_same_fixture(team1, team2, fixture):
            if fixture['Date']:
                raise Exception('  ! Fixture for {} vs {} already scheduled for {} {}'.format(team1, team2, fixture['Date'], fixture['Time']))

            fixtures[i]['Team 1']   = home_team
            fixtures[i]['Team 2']   = away_team
            fixtures[i]['Date']     = date_proposed.strftime(date_format)
            fixtures[i]['Time']     = slot['Time']
            fixtures[i]['Court']    = '1'
            fixtures[i]['Location'] = 'Main Location'
            for j, record in enumerate(fixtures_scheduled):
                if record['team'] in (home_team, away_team):
                    fixtures_scheduled[j]['fixtures'] += 1
                    fixtures_scheduled[j]['next_date'] = date_proposed + rest_delta
            print("    scheduled for {} on {} at {}".format(fixtures[i]['Time'], fixtures[i]['Date'], home_team))
            return
    raise Exception(' ! Fixture for {} vs {} is not in the fixtures.py file'.format(team1, team2))

def find_unplayed_opponent(fixtures, team):
    for fixture in fixtures:
        if not fixture['Date']:
            if team == fixture['Team 1']:
                return fixture['Team 2']
            if team == fixture['Team 2']:
                return fixture['Team 1']


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

num_matches = 10 #int((len(teams) * (len(teams)-1)) / 2)
for i in range(0, num_matches):
    print("\n\n================================ scheduling matches in batch {}".format(i+1))
    for division, teams in divisions.items():
        print("\n{}:".format(division))
        fixtures_scheduled.sort(key=lambda x: (x['fixtures'], x['next_date']))
        division_fixtures_scheduled = list(x for x in fixtures_scheduled if x['team'] in teams and x['fixtures'] <= i)
        while True:
            chosen_team_details = division_fixtures_scheduled.pop(0)
            team = chosen_team_details['team']
            for j in range(0, len(division_fixtures_scheduled)):
                opponent = division_fixtures_scheduled[j]['team']
                if not is_fixture_scheduled(team, opponent):
                    print('\nConsider {} (played {}) vs {} (played {})'.format(team, chosen_team_details['fixtures'],
                                                                         opponent, division_fixtures_scheduled[j]['fixtures']))
                    schedule_fixture(fixtures, team, opponent)
                    division_fixtures_scheduled.pop(j)
                    break
            if not len(division_fixtures_scheduled):
                break

# warn about any non-scheduled fixtures
num_unscheduled = 0
for fixture in fixtures:
    if not fixture['Date']:
        num_unscheduled += 1
        # schedule_fixture(fixtures, fixture['Team 1'], fixture['Team 2'])
if num_unscheduled:
    raise Exception("{} matches unscheduled".format(num_unscheduled))


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
            # Don't count matches as 'away' if they were played against a team from same club
            if is_same_club(team, fixture['Team 1']):
                team_stats[team]['home_matches'] += 1
            else:
                team_stats[team]['away_matches'] += 1


name_pad_len  = max(len(x) for x in team_stats.keys())
for division, teams in divisions.items():
    first_fixture = datetime.now() + timedelta(weeks=52)
    last_fixture  = datetime.now() - timedelta(weeks=52)
    print("\n==========================================================================")
    print(' Summary of {}  -  minimum {} days rest'.format(division, rest_days))
    print("==========================================================================")
    for team in teams:
        for team_name, stats in team_stats.items():
            if team == team_name:
                dates = sorted(stats['match_dates'])
                first_fixture = min(first_fixture, min(dates))
                last_fixture  = max(last_fixture, max(dates))
                days_rest = [(date-dates[i]).days for  i, date in enumerate(dates[1:])]
                print(' {:<{name_pad_len}} : {}h/{}a  {}->{}, rest {} to {} days '.format(
                    team,
                    stats['home_matches'],
                    stats['away_matches'],
                    min(dates).strftime('%d%b'),
                    max(dates).strftime('%d%b'),
                    min(days_rest),
                    max(days_rest),
                    name_pad_len=name_pad_len))
                break
    print("")
    print(' runs from {} to {}'.format(first_fixture.strftime(date_format), last_fixture.strftime(date_format)))

print("\n==========================================================================")


#if False and file_format == 'xlsx': ############### TESTING - REMOVE
if file_format == 'xlsx':
    with pandas.ExcelWriter(os.path.join(dir_path, output_filename), date_format='dd/mm/yyyy', datetime_format='HH:MM') as writer:
        for i, fixture in enumerate(fixtures):
            fixtures[i]['Date'] = datetime.strptime(fixture['Date'], date_format).date()
            fixtures[i]['Time'] = datetime.strptime(str(fixtures[i]['Time']), '%H:%M:%S').time()
        dataframe = pandas.DataFrame.from_records(fixtures, columns=fixture_file_headers)
        dataframe.to_excel(writer, index=False)
else:
    with open(os.path.join(dir_path, output_filename), 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fixture_file_headers, delimiter=',', quotechar='"')
        writer.writeheader()
        for fixture in fixtures:
            writer.writerow(fixture)
