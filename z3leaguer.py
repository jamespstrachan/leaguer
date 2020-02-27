
import csv
import pandas
from datetime import datetime, timedelta
import os

from z3 import Bool, Int, Solver, And, Or, Not, Implies, If, sat

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

weeks_in_league = (league_end_date - league_start_date).days // 7
weeks = range(0, weeks_in_league)


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


for slot in slots:
    if slot['Date']:
        slot['Date'] = datetime.strptime(slot['Date'], date_format)

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


partial_test = False
# partial_test = True
if partial_test:
    limited_teams_by_division = {
        'MENS DIVISION 1': teams_by_division['MENS DIVISION 1'],
        # 'LADIES DIVISION 4': teams_by_division['LADIES DIVISION 4'],
        'MENS DIVISION 2': teams_by_division['MENS DIVISION 2'],
        # 'MENS DIVISION 9': teams_by_division['MENS DIVISION 9'],
    }
    teams_by_division = limited_teams_by_division


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
        team1_grid        = grids_by_division[team1_division][0]
        team1_oppositions = teams_by_division[team1_division]
        team2_division    = division_for_team[team2]
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

if not partial_test:
    solver.add(conditions_between_divisions(grids_by_division))
    print('Constraining shared slots: {}'.format(solver.check()))

model = solver.model()

print('')
kpi_priority = ['home_away_imbalance', 'away_twice_at_same_club', 'repeat_of_old_fixture']
for kpi_name in kpi_priority:
    print(f'Improving KPI {kpi_name}')
    for division, (grid, match_week, away_team_grid, home_team_grid, kpis) in grids_by_division.items():
        kpi_limit = int(str(model[kpis[kpi_name]]))+1
        print(f'  {division} from {kpi_limit} → ', end='', flush=True)
        for _ in range(0, 50):
            solver.push()
            solver.add(kpis[kpi_name] < kpi_limit)

            if kpi_limit > 0 and solver.check() == sat:
                model = solver.model()
                value = int(str(model[kpis[kpi_name]]))
                if value == 0 and kpi_limit != 1:
                    kpi_limit = 1
                else:
                    kpi_limit = value
                print(f'{kpi_limit} → ', end='', flush=True)
            else:
                print('done')
                solver.pop()
                break
print('')

solver.check()
model = solver.model()


def match_date(home_team, week):
    return slots[team_slots[home_team]]['Date'] + timedelta(days=7*week)


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



# if False and file_format == 'xlsx': ############### TESTING - REMOVE
if file_format == 'xlsx':
    with pandas.ExcelWriter(os.path.join(dir_path, output_filename), date_format='dd/mm/yyyy', datetime_format='HH:MM') as writer:
        #for i, fixture in enumerate(fixtures):
            #fixtures[i]['Date'] = datetime.strptime(fixture['Date'], date_format).date()
            #fixtures[i]['Time'] = datetime.strptime(str(fixtures[i]['Time']), '%H:%M:%S').time()
        dataframe = pandas.DataFrame.from_records(fixtures, columns=fixture_file_headers)
        dataframe.to_excel(writer, index=False)
else:
    with open(os.path.join(dir_path, output_filename), 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fixture_file_headers, delimiter=',', quotechar='"')
        writer.writeheader()
        for fixture in fixtures:
            writer.writerow(fixture)
