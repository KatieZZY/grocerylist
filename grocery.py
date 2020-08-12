import pandas as pd
import requests
import sys
import sqlite3 as sql

# IMPORT US FOOD GROUPS DATABASE #
conn = sql.connect('FoodGroups.db')
c = conn.cursor()

# Drop any existing tables
c.execute('''DROP TABLE FD_GROUP''')
c.execute('''DROP TABLE FD_DES''')

# Create table - FD_GROUP
c.execute('''CREATE TABLE FD_GROUP
             ([group_id]  text,[group_name] text)''')

# Create table - FD_DES
c.execute('''CREATE TABLE FD_DES
             ([id] text, [group_id] text, [longdes] text, [shortdes] text,
             [comname] text, [manuname] text, [survey] text, [ref_desc] text,
             [refuse] text, [sciname] text, [n_factor] float,
             [pro_factor] float, [fat_factor] float, [cho_factor] float)''')

conn.commit()

# Read in downloaded and preprocessed data into data tables
read_fdgroup = pd.read_csv('sr27asc/FD_GROUP.txt', sep="^", index_col=None)
read_fdgroup['group_name'] = read_fdgroup['group_name'].str.replace('~', '',
                                                                    regex=True)
read_fdgroup['group_id'] = read_fdgroup['group_id'].str.replace('~', '',
                                                                regex=True)
read_fdgroup.to_sql('FD_GROUP', conn, if_exists='replace', index=False)

read_des = pd.read_csv('sr27asc/FOOD_DES.txt', sep="^")
read_des = read_des[['group_id', 'longdes', 'shortdes']]
read_des['group_id'] = read_des['group_id'].str.replace('~', '', regex=True)
read_des['longdes'] = read_des['longdes'].str.replace('~', '', regex=True)
read_des['shortdes'] = read_des['shortdes'].str.replace('~', '', regex=True)
read_des.to_sql('FD_DES', conn, if_exists='replace', index=False)

# FUNCTIONS TO CREATE THE GROCERY LIST #


def ingredient_parser(url_text):
    """
    accepts a a txt file url.txt with a different recipe url on each line
    For example:
    https://thewoksoflife.com/cacio-e-pepe-recipe-spicy-numbing/
    https://www.justonecookbook.com/japanese-potato-salad/
    https://tasty.co/recipe/fluffy-jiggly-japanese-cheesecake

    uses an open source engine at https://schollz.com/blog/ingredients/
    """
    # convert the url text file into a list
    with open(url_text) as f:
        urls = [line.rstrip() for line in f]

    # initiate and populate dataframe to capture all ingredients
    allrecipes = pd.DataFrame(columns=['name', 'amount', 'unit', 'comment',
                              'recipe'])
    name = []
    amount = []
    unit = []
    comment = []
    recipe = []

    for recipe in urls:
        URL = "https://ingredients.schollz.now.sh/?url=" + recipe
        r = requests.get(url=URL)
        data = r.json()

        ingredients = pd.DataFrame(data['ingredients'])

        name = list(ingredients['name'])
        amount = [i['measure']['amount'] for i in data['ingredients']]
        unit = [i['measure']['name'] for i in data['ingredients']]
        if 'comment' in ingredients.keys():
            comment = list(ingredients['comment'])
        else:
            comment = [' ' for i in data['ingredients']]
        recipe = [data['title'] for i in range(len(data['ingredients']))]

        # convert to metric
        for i, u in enumerate(unit):
            if u == 'oz' or u == 'ounces':
                amount[i] = amount[i]*28.35
                unit[i] = 'gram'
            if u == 'pound':
                amount[i] = amount[i]*454
                unit[i] = 'gram'

        thisrecipe = pd.DataFrame({'name': name, 'amount': amount,
                                   'unit': unit, 'comment': comment,
                                   'recipe': recipe})
        allrecipes = allrecipes.append(thisrecipe, ignore_index=True)

    return allrecipes


def findgroup(ingredientlist):
    """
    Takes a list of ingredients as input to form the SQL queries

    Query logic:
    Search the description in the database with the
    entire ingredient name (plural removed) and return a table of the food
    group and the number of times the ingredient occurs is listed under
    that food group.

    Some food groups which are not relevant in
    making a grocery list e.g. Restaurant Food, Native American Food etc;
    are excluded.

    Assume that the group name with the highest count is the most accurate
    food group.

    If this attempt does not return anything, try only searching for the
    second term (assume that the second term is the product and the
    first term is the detail e.g. search 'cheese' in 'blue cheese')

    """
    strquery = None
    foodgroup = []

    query = '''
            SELECT group_name, COUNT(*) as count
            FROM FD_DES
            LEFT JOIN FD_GROUP ON FD_DES.group_id = FD_GROUP.group_id
            WHERE shortdes LIKE ?
            AND FD_GROUP.group_id NOT IN ('0300', '0800', '1800', '1900',
            '2100', '2200', '2500', '3500', '3600')
            GROUP BY group_name
            ORDER BY count DESC
            LIMIT 1
            '''
    foodgroup = []
    for ing in ingredientlist:
        if ing[-1] == 's':
            ing = ing[:-1]
        strquery = '%'+ing+'%'
    # initial query
        c.execute(query, [strquery])
        try:
            group = c.fetchone()[0]
            foodgroup.append(group)
        except TypeError:
            if len(ing.split()) == 2:
                ing1, ing2 = ing.split()
                strquery = '%'+ing2+'%'
                c.execute(query, [strquery])
                try:
                    group = c.fetchone()[0]
                    foodgroup.append(group)
                except TypeError:
                    foodgroup.append(' ')
            else:
                foodgroup.append(' ')
    return foodgroup


# RUN THE FUNCTION AND CREATE GROCERY LIST
# create grocery list using the ingredient parser

URL_TEXT = sys.argv[1]
OUT_FILE = str(URL_TEXT)[:-4] + 'list.csv'

grocerylist = ingredient_parser(URL_TEXT)
# search the database and insert the foodgroup
grocerylist.insert(0, "food_group", findgroup(grocerylist['name']))
grocerylist = grocerylist.sort_values(['food_group', 'name'])
# export to csv
grocerylist.to_csv(OUT_FILE, index=False)
