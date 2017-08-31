import urllib.request
import sqlite3
import json

static_url = 'https://fantasy.premierleague.com/drf/bootstrap-static'

with urllib.request.urlopen('{}'.format(static_url)) as static_json:
    static_data = json.loads(static_json.read().decode())
current_week = 0
for entry in static_data['events']:
    if entry['is_current']:
        current_week = entry['id']

# with open('/home/admin/fplmystats/fplmystats/utils/current_season.txt') as file:
with open('C:\\Users\\seanh\\PycharmProjects\\fplmystats\\fplmystats\\utils\\current_season.txt') as file:
    for x in file:
        current_season = x
# data_file = '/home/admin/fplmystats/FPLdb.sqlite'
data_file = 'FPLdb.sqlite'
changes_file = 'C:\\Users\\seanh\\PycharmProjects\\fplmystats\\fplmystats\\utils\\daily_price_changes.txt'

field_type_INT = 'INTEGER'
field_type_TEXT = 'TEXT'


def create_season_tables():
    """
    Create table which maps team IDs to team names, run once at start of season
    Create table containing the names of every player, their ID number, position & team ID
    Run once at start of season, separate function for updating player table regularly
    """
    conn = sqlite3.connect(data_file)
    c = conn.cursor()

    with urllib.request.urlopen('{}'.format(static_url)) as url:
        data = json.loads(url.read().decode())

    # team ID table
    table_name = '{}teamIDs'.format(str(current_season))
    id_field = 'id'
    name_field = 'name'

    c.execute('CREATE TABLE "{tn}" ({idf} {fti} PRIMARY KEY, {nf} {ftt})'
              .format(tn=table_name, idf=id_field, nf=name_field, fti=field_type_INT, ftt=field_type_TEXT))

    for team in data['teams']:
        team_id = team['id']
        name = team['name']

        c.execute('INSERT INTO "{tn}" VALUES ({idv}, "{nv}")'.format(tn=table_name, idv=team_id, nv=name))

    # player ID table
    table_name = '{}playerIDs'.format(str(current_season))
    id_field = 'id'
    web_name_field = 'webname'
    first_name_field = 'firstname'
    second_name_field = 'secondname'
    position_field = 'position'
    team_id_field = 'teamID'
    price_field = 'price'

    c.execute('CREATE TABLE "{tn}" ({idf} {fti} PRIMARY KEY,\
                {wnf} {ftt}, {fnf} {ftt}, {snf} {ftt}, {psf} {fti}, {tmf} {fti}, {prf} {fti})'
              .format(tn=table_name,
                      idf=id_field,
                      wnf=web_name_field,
                      fnf=first_name_field,
                      snf=second_name_field,
                      psf=position_field,
                      tmf=team_id_field,
                      prf=price_field,
                      fti=field_type_INT,
                      ftt=field_type_TEXT))
    conn.commit()
    conn.close()


def update_player_id_table():
    """
    Update the player ID table to include new players that have been added in to the game.
    To be run periodically over the season, once a week most likely.
    """
    conn = sqlite3.connect(data_file)
    c = conn.cursor()

    table_name = '{}playerIDs'.format(str(current_season))
    c.execute('SELECT id, price FROM "{}"'.format(table_name))
    pre_list = c.fetchall()
    c.execute('DELETE FROM "{}"'.format(table_name))

    with urllib.request.urlopen('{}'.format(static_url)) as url:
        data = json.loads(url.read().decode())

    for element in data['elements']:
        player_id = element['id']
        web_name = element['web_name'].replace("'", "''")
        first_name = element['first_name'].replace("'", "''")
        second_name = element['second_name'].replace("'", "''")
        position = element['element_type']
        team_id = element['team']
        price = element['now_cost'] / 10.0

        c.execute('INSERT INTO "{tn}" VALUES ({idv}, "{wnv}", "{fnv}", "{snv}", {psv}, {tmv}, {prv})'
                  .format(tn=table_name,
                          idv=player_id,
                          wnv=web_name,
                          fnv=first_name,
                          snv=second_name,
                          psv=position,
                          tmv=team_id,
                          prv=price))

    c.execute('SELECT id, price FROM "{}"'.format(table_name))
    post_list = c.fetchall()

    conn.commit()
    conn.close()

    num_new_players = len(post_list) - len(pre_list)
    changed_ids = []
    for i in range(len(pre_list)):
        if pre_list[i][1] != post_list[i][1]:
            changed_ids.append(post_list[i][0])

    while num_new_players > 0:
        changed_ids.append(post_list[-num_new_players][0])
        num_new_players -= 1

    with open(changes_file, 'r+') as changes:
        changes.truncate()
        for item in changed_ids:
            changes.write(print_player(item))


def create_weekly_tables():
    """
    Create the weekly table for every week in the season to hold data from every player for that week
    Run once at start of season, separate function for updating tables regularly
    """
    conn = sqlite3.connect(data_file)
    c = conn.cursor()
    week = 1    # always starts at 1

    while week <= 38:
        table_name = '{}week{}'.format(str(current_season), str(week))
        fields = ['id', 'points', 'minutes', 'goals', 'assists', 'cleansheets', 'saves',
                  'goalsconceded', 'pensaves', 'yellows', 'reds', 'penmisses', 'owngoals', 'bonus']

        c.execute('CREATE TABLE "{tn}" ({} {ft} PRIMARY KEY, {} {ft}, {} {ft}, {} {ft}, {} {ft},'
                  '{} {ft}, {} {ft}, {} {ft}, {} {ft}, {} {ft}, {} {ft},{} {ft}, {} {ft}, {} {ft})'
                  .format(tn=table_name, ft=field_type_INT, *fields))
        week += 1


def update_weekly_table():
    """
    Populate the weekly data table with the latest data for that week
    To be run every day there is a game
    """
    conn = sqlite3.connect(data_file)
    c = conn.cursor()
    weekly_table_name = '{}week{}'.format(str(current_season), str(current_week))
    c.execute('DELETE FROM "{}"'.format(weekly_table_name))

    player_table_name = '{}playerIDs'.format(str(current_season))
    c.execute('SELECT * from "{}"'.format(player_table_name))

    players = c.fetchall()
    for player in players:
        player_id = player[0]
        player_url = "https://fantasy.premierleague.com/drf/element-summary/{}".format(str(player_id))

        with urllib.request.urlopen('{}'.format(player_url)) as url:
            data = json.loads(url.read().decode())

        results = [0] * 14
        results[0] = player_id
        for event in data['history']:
            if event['round'] == current_week:
                results[1] += (event['total_points'])
                results[2] += (event['minutes'])
                results[3] += (event['goals_scored'])
                results[4] += (event['assists'])
                results[5] += (event['clean_sheets'])
                results[6] += (event['saves'])
                results[7] += (event['goals_conceded'])
                results[8] += (event['penalties_saved'])
                results[9] += (event['yellow_cards'])
                results[10] += (event['red_cards'])
                results[11] += (event['penalties_missed'])
                results[12] += (event['own_goals'])
                results[13] += (event['bonus'])
        c.execute('INSERT INTO "{tn}" VALUES ({}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {})'
                  .format(tn=weekly_table_name, *results))

    conn.commit()
    conn.close()


def print_player(player_id):
    conn = sqlite3.connect(data_file)
    c = conn.cursor()

    table_name = '{}playerIDs'.format(str(current_season))
    c.execute('SELECT * FROM "{}" WHERE id = {}'.format(table_name, player_id))
    player = c.fetchone()

    if player[1] == player[3]:
        player_name = player[2] + ' ' + player[3]
    else:
        player_name = player[1]

    position = player[4]
    if position == 0:
        position_string = "GK"
    elif position == 1:
        position_string = "DEF"
    elif position == 2:
        position_string = "MID"
    else:
        position_string = "FWD"

    team_id = player[5]
    table_name = '{}teamIDs'.format(str(current_season))
    c.execute('SELECT name FROM "{}" WHERE id = {}'.format(table_name, team_id))
    team_string = c.fetchone()[0]
    price = player[6]

    return "NAME: {}; TEAM: {}; POSITION: {}; PRICE: {}\n".format(player_name, team_string, position_string, price)
