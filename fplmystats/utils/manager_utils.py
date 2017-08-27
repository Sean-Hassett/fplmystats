from collections import namedtuple
from django.conf import settings
import urllib.request
import sqlite3
import json
import math

static_url = 'https://fantasy.premierleague.com/drf/bootstrap-static'
manager_info_url = 'https://fantasy.premierleague.com/drf/entry/'

with urllib.request.urlopen('{}'.format(static_url)) as static_json:
    static_data = json.loads(static_json.read().decode())
current_week = 0
for entry in static_data['events']:
    if entry['is_current']:
        current_week = entry['id']

current_season = getattr(settings, 'CURRENT_SEASON', None)
data_file = 'FPLdb.sqlite'

MINUTES_LESS_THAN_SIXTY_VALUE = 1
MINUTES_SIXTY_PLUS_VALUE = 2
GOAL_GK_DEF_VALUE = 6
GOAL_MID_VALUE = 5
GOAL_FWD_VALUE = 4
ASSIST_VALUE = 3
CLEAN_SHEET_GK_DEF_VALUE = 4
CLEAN_SHEET_MID_VALUE = 1
SAVES_DIVIDER = 3
GOALS_CONCEDED_DIVIDER = -2
PENALTIES_SAVED_VALUE = 5
YELLOW_CARDS_VALUE = -1
RED_CARDS_VALUE = -3
PENALTIES_MISSED_VALUE = -2
OWN_GOALS_VALUE = -2


def get_name_and_team(manager_id):
    """
    Return the name and team name of the manager
    """
    names = namedtuple('names', ('manager_name', 'team_name'))
    data_url = manager_info_url + str(manager_id)
    with urllib.request.urlopen('{}'.format(data_url)) as url:
        data = json.loads(url.read().decode())

    names.manager_name = data['entry']['player_first_name'] + ' ' + data['entry']['player_last_name']
    names.team_name = data['entry']['name']
    return names


def get_stats(manager_id):
    """
    Return the data for every table in the manager view
    """
    table_data = namedtuple('table_data', ('headers', 'general_number', 'general_number_totals', 'general_points',
                                           'general_points_totals', 'positions', 'positions_totals', 'team_selection',
                                           'team_selection_totals', 'max_teams', 'squad_stats_players',
                                           'squad_stats_teams'))

    conn = sqlite3.connect(data_file)
    c = conn.cursor()
    player_table = '{}playerIDs'.format(str(current_season))
    week = 1    # always starts at 1

    table_data.general_number = []     # contains the number of goals, assists etc. for each week
    table_data.general_points = []     # contains the number of points obtained via goals, assists etc. for each week
    table_data.positions = []          # contains the number of points obtained via DEFs, MIDs etc. for each week
    table_data.team_selection = []     # contains the captain, MVP, bench information etc.
    table_data.max_teams = [[]]        # contains the best team lineup for each week

    formation_dict = {'5-4-1': 0,      # used for counting occurrences of each formation
                      '5-3-2': 0,
                      '5-2-3': 0,
                      '4-5-1': 0,
                      '4-4-2': 0,
                      '4-3-3': 0,
                      '3-5-2': 0,
                      '3-4-3': 0}

    player_apps_xi_dict = {}           # records the number of times a player has appeared in the starting XI
    player_apps_xv_dict = {}           # records the number of times a player has appeared in the squad
    player_captain_dict = {}           # records the number of times a player has been captained
    player_points_dict = {}            # records the number of points obtained via each player
    teams_dict = {}                    # records the number of times a player from each team has appeared in the XI
    price_dict = {}                    # holds prices of each player

    # populate teams dictionary with all 20 teams
    c.execute('SELECT name from "{}teamIDs"'.format(str(current_season)))
    teams = c.fetchall()
    for team in teams:
        teams_dict[team[0]] = 0

    total_points = 0
    highest_points = 0
    highest_rank = 0

    while week <= current_week:
        week_string = str(week)
        weekly_table = '{}week{}'.format(current_season, week_string)
        picks_url = 'https://fantasy.premierleague.com/drf/entry/{}/event/{}/picks'.format(manager_id, week_string)

        pitch_ids = []                  # holds ids of players who are on pitch
        bench_ids = []                  # holds ids of players who are on bench
        points_list = []                # holds a list of each players points and position, for getting max points
        points_on_pitch = 0
        bench_points = 0
        captain_id = 0
        captain_name = ''
        captain_points = 0
        captain_played = False
        vice_captain_id = 0
        vice_captain_name = ''
        vice_captain_points = 0
        vice_captain_played = False
        mvp_name = 0
        mvp_points = 0

        # add empty lists to each section to be filled with the week's data
        table_data.general_number.append([0] * 14)
        table_data.general_points.append([0] * 14)
        table_data.positions.append([0] * 6)
        table_data.team_selection.append([0] * 13)
        formation = [0, 0, 0]

        # set first element of each section to the current working week
        table_data.general_number[week - 1][0] = week
        table_data.general_points[week - 1][0] = week
        table_data.positions[week - 1][0] = week
        table_data.team_selection[week - 1][0] = week

        with urllib.request.urlopen('{}'.format(picks_url)) as url:
            data = json.loads(url.read().decode())

        captain_multiplier = 1
        bench_boost = False
        chip = data['active_chip']
        if chip == '3xc':
            table_data.team_selection[week - 1][1] = 'Triple Captain'
            captain_multiplier = 2
        elif chip == 'bboost':
            table_data.team_selection[week - 1][1] = 'Bench Boost'
            bench_boost = True
        elif chip == 'freehit':
            table_data.team_selection[week - 1][1] = 'Free Hit'
        elif chip == 'wildcard':
            table_data.team_selection[week - 1][1] = 'Wildcard'
        else:
            table_data.team_selection[week - 1][1] = '-'
        table_data.team_selection[week - 1][2] = data['entry_history']['event_transfers_cost']

        week_points = data['entry_history']['points']
        if week_points > highest_points:
            highest_points = week_points
        week_rank = data['entry_history']['rank']
        if week_rank is not None:
            if week == 1:
                highest_rank = week_rank
            else:
                if week_rank < highest_rank:
                    highest_rank = week_rank
        total_points += week_points

        for pick in data['picks']:
            if bench_boost:
                pitch_ids.append([pick['element'], pick['multiplier']])
                if pick['is_captain']:
                    captain_id = pick['element']
                if pick['is_vice_captain']:
                    vice_captain_id = pick['element']
            else:
                if pick['position'] <= 11:
                    pitch_ids.append([pick['element'], pick['multiplier']])
                else:
                    bench_ids.append(pick['element'])
                if pick['is_captain']:
                    captain_id = pick['element']
                if pick['is_vice_captain']:
                    vice_captain_id = pick['element']

        for player_id in pitch_ids:
            player_id_string = str(player_id[0])

            c.execute('SELECT webname, firstname, secondname, position, teamID, price FROM "{}" WHERE id = {}'
                      .format(player_table, player_id_string))
            result = c.fetchone()

            # set name equal to first second + second name or webname if webname different to second name
            if result[0] == result[2]:
                player_name = result[1] + ' ' + result[2]
            else:
                player_name = result[0]
            position = result[3]
            team_id = result[4]
            price = result[5]

            if player_name not in player_points_dict:
                player_points_dict[player_name] = 0
                player_apps_xv_dict[player_name] = 0
            if player_name not in player_apps_xi_dict:
                player_apps_xi_dict[player_name] = 0

            player_apps_xi_dict[player_name] += 1
            player_apps_xv_dict[player_name] += 1

            if player_name not in price_dict:
                price_dict[player_name] = price

            c.execute('SELECT name from "{}teamIDs" WHERE id = {}'.format(current_season, team_id))
            team_name = c.fetchone()[0]
            teams_dict[team_name] += 1

            c.execute('SELECT * FROM "{}" WHERE id = {}'.format(weekly_table, player_id_string))
            player_datum = c.fetchone()
            if player_datum is not None:
                if player_datum[2] > 0:  # if minutes > 0
                    points_list.append([player_datum[1], position, player_name])  # points, position, player_name
                points_on_pitch += player_datum[1]

                if player_datum[0] == captain_id:
                    captain_name = player_name
                    captain_points = player_datum[1]
                    if player_datum[2] > 0:
                        captain_played = True
                elif player_datum[0] == vice_captain_id:
                    vice_captain_name = player_name
                    vice_captain_points = player_datum[1]
                    if player_datum[2] > 0:
                        vice_captain_played = True

                # subtract clean sheets from MID's and FWD's for general_number and ignore goals conceded
                if position == 3 or position == 4:
                    table_data.general_number[week - 1][5] -= player_datum[5]
                    table_data.general_number[week - 1][7] -= player_datum[7]

                # Populate general number table
                table_data.general_number[week - 1][1:14] = [sum(n) for n in zip(
                    table_data.general_number[week - 1][1:14], player_datum[1:14])]

                # Populate general points table
                table_data.general_points[week - 1][1] += player_datum[1]                               # points
                if player_datum[2] == 0:                                                                # minutes
                    table_data.general_points[week - 1][2] += 0
                elif player_datum[2] < 60:
                    table_data.general_points[week - 1][2] += MINUTES_LESS_THAN_SIXTY_VALUE
                else:
                    table_data.general_points[week - 1][2] += MINUTES_SIXTY_PLUS_VALUE

                if position == 1 or position == 2:                                                    # goals
                    table_data.general_points[week - 1][3] += player_datum[3] * GOAL_GK_DEF_VALUE
                elif position == 3:
                    table_data.general_points[week - 1][3] += player_datum[3] * GOAL_MID_VALUE
                else:
                    table_data.general_points[week - 1][3] += player_datum[3] * GOAL_FWD_VALUE

                table_data.general_points[week - 1][4] += player_datum[4] * ASSIST_VALUE              # assists

                if position == 1 or position == 2:                                                    # clean sheets
                    table_data.general_points[week - 1][5] += player_datum[5] * CLEAN_SHEET_GK_DEF_VALUE
                elif position == 3:
                    table_data.general_points[week - 1][5] += player_datum[5] * CLEAN_SHEET_MID_VALUE

                table_data.general_points[week - 1][6] += math.floor(player_datum[6] / SAVES_DIVIDER)  # saves

                if position == 1 or position == 2:                                                    # goals conceded
                    table_data.general_points[week - 1][7] += math.ceil(player_datum[7] / GOALS_CONCEDED_DIVIDER)

                table_data.general_points[week - 1][8] += player_datum[8] * PENALTIES_SAVED_VALUE     # penalties saved
                table_data.general_points[week - 1][9] += player_datum[9] * YELLOW_CARDS_VALUE        # yellow cards
                table_data.general_points[week - 1][10] += player_datum[10] * RED_CARDS_VALUE         # red cards
                table_data.general_points[week - 1][11] += player_datum[11] * PENALTIES_MISSED_VALUE  # penalties missed
                table_data.general_points[week - 1][12] += player_datum[12] * OWN_GOALS_VALUE         # own goals
                table_data.general_points[week - 1][13] += player_datum[13]                           # bonus points

                player_points_dict[player_name] += player_datum[1]

                if player_datum[1] > mvp_points:
                    mvp_points = player_datum[1]
                    mvp_name = player_name

                if position == 1:
                    table_data.positions[week - 1][2] += player_datum[1]
                elif position == 2:
                    table_data.positions[week - 1][3] += player_datum[1]
                    formation[0] += 1
                elif position == 3:
                    table_data.positions[week - 1][4] += player_datum[1]
                    formation[1] += 1
                elif position == 4:
                    table_data.positions[week - 1][5] += player_datum[1]
                    formation[2] += 1

        for player_id in bench_ids:
            player_id_string = str(player_id)

            c.execute('SELECT webname, firstname, secondname, position, price FROM "{}" WHERE id = {}'
                      .format(player_table, player_id_string))
            result = c.fetchone()

            # set name equal to first second + second name or webname if webname different to second name
            if result[0] == result[2]:
                player_name = result[1] + ' ' + result[2]
            else:
                player_name = result[0]
            position = result[3]
            price = result[4]

            if player_name not in player_points_dict:
                player_points_dict[player_name] = 0
                player_apps_xv_dict[player_name] = 0

            player_apps_xv_dict[player_name] += 1

            if player_name not in price_dict:
                price_dict[player_name] = price

            c.execute('SELECT * FROM "{}" WHERE id = {}'.format(weekly_table, player_id_string))
            player_datum = c.fetchone()

            if player_datum is not None:
                if player_datum[0] == captain_id:
                    captain_name = player_name
                    captain_points = player_datum[1]
                    if player_datum[2] > 0:
                        captain_played = True
                elif player_datum[0] == vice_captain_id:
                    vice_captain_name = player_name
                    vice_captain_points = player_datum[1]
                    if player_datum[2] > 0:
                        vice_captain_played = True

                if player_datum[2] > 0:
                    points_list.append([player_datum[1], position, player_name])  # points, position, player_name
                bench_points += player_datum[1]

        string_formation = '4-4-2'  # default formation if db not updated
        if formation == [5, 4, 1]:
            string_formation = '5-4-1'
        elif formation == [5, 3, 2]:
            string_formation = '5-3-2'
        elif formation == [5, 2, 3]:
            string_formation = '5-2-3'
        elif formation == [4, 5, 1]:
            string_formation = '4-5-1'
        elif formation == [4, 4, 2]:
            string_formation = '4-4-2'
        elif formation == [4, 3, 3]:
            string_formation = '4-3-3'
        elif formation == [3, 5, 2]:
            string_formation = '3-5-2'
        elif formation == [3, 4, 3]:
            string_formation = '3-4-3'

        formation_dict[string_formation] += 1
        table_data.positions[week - 1][1] = string_formation

        # TODO show best possible team in modal window
        max_points_on_pitch = 0
        points_list.sort()
        points_list = points_list[::-1]
        max_points_team = []

        if not bench_boost:
            try:
                max_points_on_pitch += next(item[0] for item in points_list if item[1] == 1)      # 1 goalkeeper
                max_points_team.append(next(item for item in points_list if item[1] == 1))
                points_list.remove(next(item for item in points_list if item[1] == 1))
                points_list.remove(next(item for item in points_list if item[1] == 1))
            except StopIteration:
                ''
            for i in range(3):                                                                    # 3 defenders
                try:
                    max_points_on_pitch += next(item[0] for item in points_list if item[1] == 2)
                    max_points_team.append(next(item for item in points_list if item[1] == 2))
                    points_list.remove(next(item for item in points_list if item[1] == 2))
                except StopIteration:
                    ''
            for i in range(2):                                                                    # 2 midfielders
                try:
                    max_points_on_pitch += next(item[0] for item in points_list if item[1] == 3)
                    max_points_team.append(next(item for item in points_list if item[1] == 3))
                    points_list.remove(next(item for item in points_list if item[1] == 3))
                except StopIteration:
                    ''
            try:
                max_points_on_pitch += next(item[0] for item in points_list if item[1] == 4)      # 1 forward
                max_points_team.append(next(item for item in points_list if item[1] == 4))
                points_list.remove(next(item for item in points_list if item[1] == 4))
            except StopIteration:
                ''
            for i in range(4):                                                                    # 4 remaining players
                try:
                    max_points_on_pitch += next(item[0] for item in points_list)
                    max_points_team.append(next(item for item in points_list))
                    points_list.remove(next(item for item in points_list))
                except StopIteration:
                    ''
            bench_potential_lost = max_points_on_pitch - points_on_pitch
        else:
            bench_potential_lost = 0

        # assign the captain in max team and then sort by position
        if max_points_team:
            max_points_team.sort()
            max_points_team[-1][2] = max_points_team[-1][2] + ' (C)'
            max_points_team[-1][0] = max_points_team[-1][0] * 2
            max_points_team = sorted(max_points_team, key=lambda l: l[1])
            for player in max_points_team:
                if player[1] == 1:
                    player[1] = 'GK'
                elif player[1] == 2:
                    player[1] = 'DEF'
                elif player[1] == 3:
                    player[1] = 'MID'
                else:
                    player[1] = 'FWD'
            table_data.max_teams.append(max_points_team)

        if captain_played or not vice_captain_played:
            table_data.team_selection[week - 1][3] = captain_name
            table_data.team_selection[week - 1][4] = captain_points * captain_multiplier
            if captain_name not in player_captain_dict:
                player_captain_dict[captain_name] = 0
            player_captain_dict[captain_name] += 1
        else:
            table_data.team_selection[week - 1][3] = vice_captain_name
            table_data.team_selection[week - 1][4] = vice_captain_points
            if vice_captain_name not in player_captain_dict:
                player_captain_dict[vice_captain_name] = 0
            player_captain_dict[vice_captain_name] += 1

        table_data.team_selection[week - 1][5] = mvp_name
        table_data.team_selection[week - 1][6] = mvp_points
        table_data.team_selection[week - 1][7] = (mvp_points - captain_points) * captain_multiplier
        table_data.team_selection[week - 1][8] = bench_points
        table_data.team_selection[week - 1][9] = bench_potential_lost
        table_data.team_selection[week - 1][10] = table_data.general_points[week - 1][1] +\
            table_data.team_selection[week - 1][4] - table_data.team_selection[week - 1][2]
        table_data.team_selection[week - 1][12] = table_data.team_selection[week - 1][7] +\
            table_data.team_selection[week - 1][9]
        table_data.team_selection[week - 1][11] = table_data.team_selection[week - 1][10] +\
            table_data.team_selection[week - 1][12]

        week += 1

    table_data.general_number_totals = [n for n in zip(*table_data.general_number)][1:15]
    table_data.general_number_totals = [sum(n) for n in table_data.general_number_totals]
    table_data.general_points_totals = [n for n in zip(*table_data.general_points)][1:15]
    table_data.general_points_totals = [sum(n) for n in table_data.general_points_totals]

    table_data.positions_totals = [n for n in zip(*table_data.positions)][2:7]
    table_data.positions_totals = [sum(n) for n in table_data.positions_totals]

    # TODO add triple captain points to total captain points
    table_data.team_selection_totals = [0]*7
    table_data.team_selection_totals[0] = sum(entry[2] for entry in table_data.team_selection)    # transfer cost
    table_data.team_selection_totals[1] = sum(entry[4] for entry in table_data.team_selection)    # captain points
    table_data.team_selection_totals[2] = sum(entry[6] for entry in table_data.team_selection)    # mvp total
    table_data.team_selection_totals[3] = sum(entry[7] for entry in table_data.team_selection)    # captain lost
    # table_data.team_selection_totals[4] = sum(week[8] for entry in table_data.team_selection)    # bench points
    table_data.team_selection_totals[4] = sum(entry[9] for entry in table_data.team_selection)    # bench lost
    table_data.team_selection_totals[5] = sum(entry[11] for entry in table_data.team_selection)   # max possible
    table_data.team_selection_totals[6] = sum(entry[12] for entry in table_data.team_selection)   # all lost

    table_data.squad_stats_players = []
    for player in player_apps_xv_dict:
        name = player
        weeks_in_xi = 0
        weeks_in_xv = player_apps_xv_dict[player]
        weeks_captain = 0
        points = 0
        player_value = price_dict[player]

        if player in player_apps_xi_dict:
            weeks_in_xi = player_apps_xi_dict[player]
        if player in player_captain_dict:
            weeks_captain = player_captain_dict[player]
        if player in player_points_dict:
            points = player_points_dict[player]

        # TODO fix negative points ppg & vapm
        points_per_game = 0.0
        if weeks_in_xi != 0:
            points_per_game = round(points / weeks_in_xi, 1)

        value_added_per_million = 0.0
        if weeks_in_xi != 0:
            value_added_per_million = round((points_per_game - 2) / player_value, 1)

        table_data.squad_stats_players.append([name, weeks_in_xi, weeks_in_xv, weeks_captain, points,
                                              points_per_game, value_added_per_million])

    table_data.squad_stats_teams = []
    for team in teams_dict:
        table_data.squad_stats_teams.append([team, teams_dict[team]])

    table_data.headers = [0] * 7

    table_data.headers[0] = sum(entry[10] for entry in table_data.team_selection)
    table_data.headers[1] = highest_points
    table_data.headers[2] = highest_rank
    table_data.headers[3] = max(player_captain_dict, key=player_captain_dict.get)
    table_data.headers[4] = max(player_points_dict, key=player_points_dict.get)
    table_data.headers[5] = player_points_dict[table_data.headers[4]]
    table_data.headers[6] = max(formation_dict, key=formation_dict.get)

    return table_data