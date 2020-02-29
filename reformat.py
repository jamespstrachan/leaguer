
import csv
import pandas
from datetime import datetime, timedelta
import os

file_format       = 'xlsx'
file_prefix       = ''
fixtures_filename = 'results 2020Feb26 08.40.24.DRAFT2.xlsx'
output_filename   = fixtures_filename['0:-5'] + ' reformatted.xlsx'
old_fixtures_filename = '{}old_fixtures.{}'.format(file_prefix, file_format)
slots_filename    = '{}slots.{}'.format(file_prefix, file_format)
date_format       = '%d/%m/%Y'
newline           = "\r\n"
dir_path          = os.path.dirname(os.path.realpath(__file__))

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
played_in_old_fixtures = [(x['Team 1'], x['Team 2']) for x in old_fixtures]


fixture_file_headers = list(fixture_file_headers)
if 'rematch' not in fixture_file_headers:
    fixture_file_headers.append('rematch')

for fixture in fixtures:
    if (fixture['Team 1'], fixture['Team 2']) in played_in_old_fixtures:
        fixture['rematch'] = 'repeat'
    elif (fixture['Team 2'], fixture['Team 1']) in played_in_old_fixtures:
        fixture['rematch'] = 'reversed'
    else:
        fixture['rematch'] = '-'


# if False and file_format == 'xlsx': ############### TESTING - REMOVE
if file_format == 'xlsx':
    with pandas.ExcelWriter(os.path.join(dir_path, output_filename), date_format='dd/mm/yyyy', datetime_format='HH:MM') as writer:
        for i, fixture in enumerate(fixtures):
            if not fixture['Date']:
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
