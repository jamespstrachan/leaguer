import csv
import pandas
from datetime import datetime, timedelta
import os
import argparse

from z3 import Bool, Int, Solver, And, Or, Not, Implies, If, sat, set_param

set_param('parallel.enable', True)
set_param('parallel.threads.max', 4)

parser = argparse.ArgumentParser()
parser.add_argument("directory", type=str, help="path to directory containing the fixtures.xlsx and slots.xlsx files")
parser.add_argument("start_date", type=str, help="start date for the competition in format 31/12/2021")
parser.add_argument("-w", "--weeks", type=int, default=8, help="how many weeks from start_date the competition should run for")
parser.add_argument("-r", "--restdays", type=int, default=5,
                    help="the minimum number of days between successive fixtures for any team. "
                        +"1 would mean teams could play a second match the day after a first")
parser.add_argument("-s", "--spread", type=int, default=1, help="allows the weeks of the competition to be spread out, "+
                                                                "eg =2 for interleaving with another competition on alternating weeks")
parser.add_argument("-c", "--csv", action="store_true", help="ingest and output csv files instead of xlsx files")

args = parser.parse_args()

reformat_file_only = False # Set True to skip the constraint solving and just load and re-save the file (used to improve formatting)
partial_test       = False # Set True to only process a couple of divisions, detailed below
file_format       = 'csv' if args.csv else 'xlsx'
rest_days         = args.restdays
file_prefix       = args.directory.rstrip('/')
fixtures_filename = '{}/fixtures.{}'.format(file_prefix, file_format)
old_fixtures_filename = '{}/old_fixtures.{}'.format(file_prefix, file_format)
slots_filename    = '{}/slots.{}'.format(file_prefix, file_format)
date_format       = '%d/%m/%Y'
newline           = "\r\n"
dir_path          = os.path.dirname(os.path.realpath(__file__))
league_start_date = datetime.strptime(args.start_date, date_format)
#league_end_date   = datetime.strptime('13/11/2020', date_format)
#weeks_in_league = (league_end_date - league_start_date).days // 7
weeks_in_league = args.weeks
weeks_spread = args.spread
weeks = range(0, weeks_in_league)
output_filename   = '{}/results-{}-{}-{}wks-{}restdays.{}'.format(file_prefix, args.directory.split('-')[-1], league_start_date.strftime('%d%b'), weeks_in_league, rest_days, file_format)

if file_format == 'xlsx':
    # make fixtures list of dicts with keys: Date,Time,League Type,Event,Draw,Nr,Team 1,Team 2,Court,Location
    with open(fixtures_filename, "rb") as xlsxfile:
        # New pandas loading error around Inferring datetime64[ns] might be solved through explicity use of dtype or converter
        # see https://stackoverflow.com/questions/42958217/pandas-read-excel-datetime-converter
        fixtures_dataframe = pandas.read_excel(xlsxfile, engine="openpyxl", na_filter=False, dtype={'Date': 'datetime64'})
        fixture_file_headers = fixtures_dataframe.columns
        fixtures = fixtures_dataframe.to_dict(orient="records")
    # make old fixtures list of dicts with keys: Date,Time,League Type,Event,Draw,Nr,Team 1,Team 2,Court,Location
    try:
        with open(old_fixtures_filename, "rb") as xlsxfile:
            old_fixtures_dataframe = pandas.read_excel(xlsxfile, engine="openpyxl", na_filter=False)
            old_fixtures = old_fixtures_dataframe.to_dict(orient="records")
    except IOError:
        print('no old fixture file found, home/away won\'t be reversed based on a previous league')
        old_fixtures = []

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

all_teams_in_fixtures = set(list(x['Team 1'] for x in fixtures) + list(x['Team 2'] for x in fixtures))
all_teams_in_slots = list(x['Team 1'] for x in slots if x['Team 1']) + list(x['Team 2'] for x in slots if x['Team 2'])

print('{} teams found in fixtures file - {} found in slots file'.format(len(all_teams_in_fixtures), len(all_teams_in_slots)))

dupes_in_slots = set([x for x in all_teams_in_slots if all_teams_in_slots.count(x) > 1])
if dupes_in_slots:
    print("The following teams appear more than once in the slots file:")
    print(dupes_in_slots)
    exit()

teams_in_fixtures_not_slots = all_teams_in_fixtures - set(all_teams_in_slots)
if teams_in_fixtures_not_slots:
    print("The following teams appear in the fixtures file but not in the slots file:")
    print(teams_in_fixtures_not_slots)
    exit()

teams_in_slots_not_fixtures =  set(all_teams_in_slots) - all_teams_in_fixtures
if teams_in_slots_not_fixtures:
    print("The following teams appear in the slots file but not in the fixtures file:")
    print(teams_in_slots_not_fixtures)
    exit()

first_slot_dates = list(datetime.strptime(x['Date'], date_format) for x in slots)
max_date, min_date = max(first_slot_dates), min(first_slot_dates)
if max_date - min_date > timedelta(days=7):
    print("The earliest date in slots file {} is more than a week before the latest date {}".format(min_date.strftime(date_format),
                                                                                                    max_date.strftime(date_format)))
    print("The slots file should contain a slot for every team in the first week of competition")
    exit()


if not reformat_file_only:
    for slot in slots:
        if slot['Date']:
            slot['Date'] = datetime.strptime(slot['Date'], date_format) if isinstance(slot['Date'], str) else slot['Date']

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


    teams_by_division = {}
    division_for_team = {}
    for fixture in fixtures:
        division = fixture['Draw']
        team = fixture['Team 1']
        if division not in teams_by_division:
            teams_by_division[division] = []
        if team not in teams_by_division[division]:
            teams_by_division[division].append(team)
        if team not in division_for_team:
            division_for_team[team] = division


    if partial_test:
        limited_teams_by_division = {
            # 'MENS DIVISION 2': teams_by_division['MENS DIVISION 2'],
            'LADIES DIVISION 7': teams_by_division['LADIES DIVISION 7'],
            'LADIES DIVISION 4': teams_by_division['LADIES DIVISION 4'],
            'LADIES DIVISION 5': teams_by_division['LADIES DIVISION 5'],
            'LADIES DIVISION 6': teams_by_division['LADIES DIVISION 6'],
            # 'MENS DIVISION 9': teams_by_division['MENS DIVISION 9'],
            # 'MIXED DIVISION 1': teams_by_division['MIXED DIVISION 1'],
            # 'MIXED DIVISION 2': teams_by_division['MIXED DIVISION 2'],
        }
        #teams_by_division = limited_teams_by_division

        # special case REMOVE
        del teams_by_division['LADIES DIVISION 1']

    grids_by_division = {}
    for division, teams in teams_by_division.items():
        grid = {}
        match_week = {}
        away_team_grid = {}
        home_team_grid = {}
        for home_team in teams:
            for away_team in teams:
                match_week[home_team, away_team] = Int(f'{home_team}_vs_{away_team}_in_week')
                for week in weeks:
                    grid[home_team, away_team, week] = Bool(f'{home_team}_vs_{away_team}_week_{week}')

            for week in weeks:
                away_team_grid[home_team, week] = Int(f'{home_team}_home_in_week_{week}_to')

        for away_team in teams:
            for week in weeks:
                home_team_grid[away_team, week] = Int(f'{away_team}_away_in_week_{week}_to')

        kpis = {
            'home_away_imbalance':         Int(f'{division} home_away_imbalance'),
            'away_twice_at_same_club':     Int(f'{division} away_twice_at_same_club'),
            'repeat_of_old_fixture':       Int(f'{division} repeat_of_old_fixture'),
        }

        grids_by_division[division] = (grid, match_week, away_team_grid, home_team_grid, kpis)


    def condition_grid_match_week(grid, match_week, teams):
        return And(*(grid[home_team, away_team, week] == (match_week[home_team, away_team] == week)
                     for home_team in teams
                     for away_team in teams
                     for week in weeks))

    def condition_not_both_home_away(match_week, teams):
        return And(*(Or(match_week[team1, team2] == -1,
                        match_week[team2, team1] == -1)
                     for team1 in teams
                     for team2 in teams))

    def condition_one_of_home_away(match_week, teams):
        return And(*((match_week[team1, team2] == -1)
                     != (match_week[team2, team1] == -1)
                     for team1 in teams
                     for team2 in teams
                     if team1 != team2))

    def condition_match_week_valid(match_week, teams):
        return And(*(And(match_week[team1, team2] >= -1,
                         match_week[team1, team2] <= max(weeks))
                     for team1 in teams
                     for team2 in teams))

    def condition_grid_away_team_grid(grid, away_team_grid, teams):
        return And(*(grid[home_team, away_team, week] == (away_team_grid[home_team, week] == away_team_idx)
                     for home_team in teams
                     for away_team_idx, away_team in enumerate(teams)
                     for week in weeks))

    def condition_away_team_grid_valid(away_team_grid, teams):
        return And(*(And(away_team_grid[home_team, week] >= -1,
                         away_team_grid[home_team, week] < len(teams))
                     for home_team in teams
                     for week in weeks))

    def condition_grid_home_team_grid(grid, home_team_grid, teams):
        return And(*(grid[home_team, away_team, week] == (home_team_grid[away_team, week] == home_team_idx)
                     for home_team_idx, home_team in enumerate(teams)
                     for away_team in teams
                     for week in weeks))

    def condition_home_team_grid_valid(home_team_grid, teams):
        return And(*(And(home_team_grid[away_team, week] >= -1,
                         home_team_grid[away_team, week] < len(teams))
                     for away_team in teams
                     for week in weeks))


    # Old constraints which should be superseded by constraints on new projections, such as
    # condition_grid_match_week()

    def condition_match_happens_once(grid, teams):
        pairing_happens = []
        plays_self = []
        plays_both = []
        for team1 in teams:
            for team2 in teams:
                if team1 == team2:
                    plays_self.append(Or(*(grid[team1, team2, week] for week in weeks)))
                else:
                    plays_home = (grid[team1, team2, week] for week in weeks)
                    plays_away = (grid[team2, team1, week] for week in weeks)
                    pairing_happens.append(Or(*plays_home, *plays_away))
                    plays_both.append(And(Or(*plays_home), Or(*plays_away)))
        return And(*pairing_happens, Not(Or(*plays_self)), Not(Or(*plays_both)))


    def condition_play_once_per_week(grid, teams):
        play_once = []
        for week in weeks:
            for home_team in teams:
                for away_team in teams:
                    home_other_home = Or(*(grid[home_team, opp, week] for opp in teams if opp != away_team))
                    home_any_away   = Or(*(grid[opp, home_team, week] for opp in teams))
                    away_any_home   = Or(*(grid[away_team, opp, week] for opp in teams))
                    away_other_away = Or(*(grid[opp, away_team, week] for opp in teams if opp != home_team))
                    this_match                = grid[home_team, away_team, week]
                    any_other_match_this_week = Or(home_other_home, home_any_away, away_any_home, away_other_away)
                    play_once.append(Implies(this_match, Not(any_other_match_this_week)))
        return And(*play_once)


    def condition_enough_rest(grid, teams):
        enough_rest = []
        rest_period = timedelta(days=rest_days)
        for week in weeks[:-1]: # don't check future rest for final week's fixtures
            home_dates_by_team = {team: slots[team_slots[team]]['Date'] + timedelta(days=7*week) for team in teams}
            for home_team in teams:
                for away_team in teams:
                    this_match_date = home_dates_by_team[home_team]
                    home_team_plays_away_too_soon = []
                    away_team_plays_away_too_soon = []
                    for next_team in teams:
                        next_match_date = home_dates_by_team[next_team] + timedelta(days=7)
                        if next_match_date < this_match_date + rest_period:
                            home_team_plays_away_too_soon.append(grid[next_team, home_team, week+1])
                            away_team_plays_away_too_soon.append(grid[next_team, away_team, week+1])

                    next_away_home_date = home_dates_by_team[away_team] + timedelta(days=7)
                    away_team_plays_at_home_too_soon = False
                    if next_away_home_date < this_match_date + rest_period:
                        away_team_plays_at_home_too_soon = Or(*(grid[away_team, next_team, week+1] for next_team in teams))

                    this_match             = grid[home_team, away_team, week]
                    # we don't worry about home_team playing at home too soon as that's their weekly
                    # and we expect them to be prepared to play back-to-back home matches
                    matches_too_soon_after = Or(*home_team_plays_away_too_soon,
                                                *away_team_plays_away_too_soon,
                                                away_team_plays_at_home_too_soon)
                    enough_rest.append(Implies(this_match, Not(matches_too_soon_after)))
        return And(*enough_rest)


    def is_same_club(team1, team2):
        """ returns true if the club names are identical except for the trailing team number """
        return team1[0:-2] == team2[0:-2]

    def condition_same_club_teams_play_first(grid, teams):
        same_club = []
        team_can_play_on_week = {team: weeks[0] for team in teams}
        for i, team1 in enumerate(teams):
            for team2 in teams[i+1:]:
                if is_same_club(team1, team2):
                    week = max(team_can_play_on_week[team1], team_can_play_on_week[team2])
                    same_club.append(Or(grid[team1, team2, week] == True, grid[team2, team1, week] == True))
                    team_can_play_on_week[team1] = week + 1
                    team_can_play_on_week[team2] = week + 1
        return And(*same_club)


    def condition_shared_slot_not_double_booked(grids_by_division):
        not_double_booked = []
        for slot in slots:
            if not slot['Team 2']:
                continue
            team1 = slot['Team 1']
            team2 = slot['Team 2']
            team1_division    = division_for_team[team1]
            if partial_test and team1_division not in grids_by_division:  ## temporary fudge while removing div
                continue
            team1_grid        = grids_by_division[team1_division][0]
            team1_oppositions = teams_by_division[team1_division]
            team2_division    = division_for_team[team2]
            if partial_test and team2_division not in grids_by_division:  ## temporary fudge while removing div
                continue
            team2_grid        = grids_by_division[team2_division][0]
            team2_oppositions = teams_by_division[team2_division]
            for week in weeks:
                team1_at_home = Or(*(team1_grid[team1, opp, week] for opp in team1_oppositions))
                team2_at_home = Or(*(team2_grid[team2, opp, week] for opp in team2_oppositions))
                not_double_booked.append(Not(And(team1_at_home, team2_at_home)))
        return And(*not_double_booked)



    def abs(x):
        return If(x >= 0,x,-x)

    def count_home_away_games_diff(home_team_grid, away_team_grid, teams):
        total_difference = 0
        for team in teams:
            home_games = sum(If(away_team_grid[team, week] >= 0, 1, 0)
                             for week in weeks)
            away_games = sum(If(home_team_grid[team, week] >= 0, 1, 0)
                             for week in weeks)

            difference = abs(home_games - away_games)
            # out-by-one is fine because 4h/3a is not improvable
            total_difference += If(difference == 1, 0, difference)
        return total_difference


    def count_away_twice_at_same_club(grid, teams):
        total_same_club_aways = 0
        for i, team1 in enumerate(teams):
            for team2 in teams[i+1:]:
                if is_same_club(team1, team2):
                    for team in teams:
                        plays_team1_away = Or(*(grid[team1, team, week] for week in weeks))
                        plays_team2_away = Or(*(grid[team2, team, week] for week in weeks))
                        total_same_club_aways += If(And(plays_team1_away, plays_team2_away), 1, 0)
        return total_same_club_aways


    played_in_old_fixtures = [(x['Team 1'], x['Team 2']) for x in old_fixtures]
    def count_repeat_of_old_fixture(grid, teams):
        total_repeat_of_old_fixture = 0
        for team1 in teams:
            for team2 in teams:
                if (team1, team2) in played_in_old_fixtures:
                    repeat_of_old_fixture = Or(*(grid[team1, team2, week] for week in weeks))
                    total_repeat_of_old_fixture += If(repeat_of_old_fixture, 1, 0)
        return total_repeat_of_old_fixture


    def conditions_for_division(grid, match_week, away_team_grid, home_team_grid, teams):
        return And(
                   ## These two superseded by the following set of 8
                   condition_match_happens_once(grid, teams),
                   condition_play_once_per_week(grid, teams),
                   ##
                   condition_grid_match_week(grid, match_week, teams),
                   condition_not_both_home_away(match_week, teams),
                   condition_one_of_home_away(match_week, teams),
                   condition_match_week_valid(match_week, teams),
                   condition_grid_away_team_grid(grid, away_team_grid, teams),
                   condition_away_team_grid_valid(away_team_grid, teams),
                   condition_grid_home_team_grid(grid, home_team_grid, teams),
                   condition_home_team_grid_valid(home_team_grid, teams),

                   condition_enough_rest(grid, teams),
                   condition_same_club_teams_play_first(grid, teams),
                   True)


    def conditions_between_divisions(grids_by_division):
        return And(
                   condition_shared_slot_not_double_booked(grids_by_division),
                   True)


    def kpis_for_division(grid, match_week, away_team_grid, home_team_grid, kpis):
        return And(
                   kpis['home_away_imbalance']     == count_home_away_games_diff(home_team_grid, away_team_grid, teams),
                   kpis['away_twice_at_same_club'] == count_away_twice_at_same_club(grid, teams),
                   kpis['repeat_of_old_fixture']   == count_repeat_of_old_fixture(grid, teams),
                   True
                   )


    solver = Solver()
    for division, (grid, match_week, away_team_grid, home_team_grid, kpis) in grids_by_division.items():
        teams = teams_by_division[division]
        solver.add(conditions_for_division(grid, match_week,
                                           away_team_grid, home_team_grid,
                                           teams))
        solver.add(kpis_for_division(grid, match_week, away_team_grid, home_team_grid, kpis))
        print('provisional {}: {}'.format(division, solver.check()))

    solver.add(conditions_between_divisions(grids_by_division))
    print('Constraining shared slots: {}'.format(solver.check()))

    model = solver.model()

    print('')
    kpi_priority = ['home_away_imbalance', 'away_twice_at_same_club', 'repeat_of_old_fixture']
    for kpi_name in kpi_priority:
        print(f'Testing KPI {kpi_name}')

        # test with all < 1
        print(f'  All divisions  : <1? ', end='', flush=True)
        solver.push()
        solver.add(And(*(kpis[kpi_name] < 1 for _,(_,_,_,_,kpis) in grids_by_division.items())))

        if solver.check() == sat:
            print('yes!')
            continue
        else:
            print('no, try individually...')
            solver.pop()

        # else test with each < 1,  backing off as needed
        for division, (grid, match_week, away_team_grid, home_team_grid, kpis) in grids_by_division.items():
            kpi_limit = 1
            print(f'  {division:<30}: ', end='', flush=True)
            for _ in range(0, 50):
                print(f'<{kpi_limit}? ', end='')
                solver.push()
                solver.add(kpis[kpi_name] < kpi_limit)

                if solver.check() == sat:
                    print('yes!')
                    break
                else:
                    kpi_limit += 1
                    print('no, ', end='', flush=True)
                    solver.pop()

    print('')

    model = solver.model()


    def match_date(home_team, week):
        return slots[team_slots[home_team]]['Date'] + timedelta(days=7*week*weeks_spread)


    scheduled_matches = {}
    for division, (grid, match_week, away_team_grid, home_team_grid, kpis) in grids_by_division.items():
        print(f"= {division} =========== ")
        teams = teams_by_division[division]
        print(" ↓ home team {:>26}".format('   \    away team → \t'), end='')
        print('\t'.join(f'({idx+1})' for idx in range(0, len(teams))))
        for home_idx, home_team in enumerate(teams):
            matches = {i: match_date(home_team, week)
                       for i, away_team in enumerate(teams)
                       for week in weeks
                       if model[grid[home_team, away_team, week]]}

            print(f"({home_idx+1}){home_team:>31} :", end='')
            for i in range(0, len(teams)):
                if i in matches:
                    scheduled_matches[home_team, teams[i]] = matches[i]
                    print(f'\t{matches[i].strftime("%d%b")}', end='')
                else:
                    print('\t -', end='')
            print('')

        print('Home/Away imbalance     = {}'.format(model[kpis['home_away_imbalance']]))
        print('Away twice at same club = {}'.format(model[kpis['away_twice_at_same_club']]))
        print('Repeat of old fixture   = {}'.format(model[kpis['repeat_of_old_fixture']]))

        # for team1 in teams:
            # for team2 in teams:
                # for week in weeks:
                    # if model[grid[team1, team2, week]]:
                        # print(f'{team1} plays {team2} on {match_date(team1, week)}')
        print('')

        ##  Alternative output of matches for each team
        # for team1 in teams:
            # print(f'\n {team1}:', end='')
            # for team2 in teams:
                # for week in weeks:
                    # if model[grid[team1, team2, week]]:
                        # print(f"{team2} on wk{week}, ", end='')
        # print('')


    new_column_headers = []
    for fixture in fixtures:
        team1 = fixture['Team 1']
        team2 = fixture['Team 2']

        if (team1, team2) in scheduled_matches:
            fixture['Team 1']   = team1
            fixture['Team 2']   = team2
            fixture['Date']     = scheduled_matches[team1, team2].strftime(date_format)
            fixture['Time']     = slots[team_slots[team1]]['Time']
        elif (team2, team1) in scheduled_matches:
            fixture['Team 1']   = team2
            fixture['Team 2']   = team1
            fixture['Date']     = scheduled_matches[team2, team1].strftime(date_format)
            fixture['Time']     = slots[team_slots[team2]]['Time']
        elif partial_test:
            continue
        else:
            raise Exception(f'Match between {team1} and {team2} not found in scheduled matches list')

        fixture['Court']    = '1'
        fixture['Location'] = 'Main Location'

        teams = teams_by_division[division_for_team[team1]]
        has_team_columns = {f'has_team_{idx}': 1 if team_name in (team1, team2) else 0
                            for idx, team_name in enumerate(teams, 1)}
        new_column_headers += has_team_columns.keys()
        fixture.update(has_team_columns)

    fixture_file_headers = list(fixture_file_headers) + sorted(list(set(new_column_headers)))


# Check if there are clashes on shared slots
slot_buddies = []
dates_by_team1 = {}
dates_by_team2 = {}
for slot in slots:
    if slot['Team 1'] and slot['Team 2']:
        slot_buddies.append((slot['Team 1'], slot['Team 2']))
        dates_by_team1[slot['Team 1']] = []
        dates_by_team2[slot['Team 2']] = []
for fixture in fixtures:
    if not fixture['Date']:
        continue
    if fixture['Team 1'] in dates_by_team1.keys():
        dates_by_team1[fixture['Team 1']].append(fixture['Date'])
    if fixture['Team 1'] in dates_by_team2.keys():
        dates_by_team2[fixture['Team 1']].append(fixture['Date'])
for team1, team2 in slot_buddies:
    shared_home_dates = list(x for x in set(dates_by_team1[team1]) if x in set(dates_by_team2[team2]))
    if len(shared_home_dates):
        print(' ! shared slot clash: {} and {} clash on {}'.format(team1, team2, ", ".join(x.strftime('%d %b') for x in shared_home_dates)))


# if False and file_format == 'xlsx': ############### TESTING - REMOVE
if file_format == 'xlsx':
    with pandas.ExcelWriter(os.path.join(dir_path, output_filename), date_format='dd/mm/yyyy', datetime_format='HH:MM:SS') as writer:
        for i, fixture in enumerate(fixtures):
            if partial_test and not fixture['Date']:
                continue
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
