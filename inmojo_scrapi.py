#!/usr/bin/env python

"""
InMojo ScrAPI web scraper API script
2015-01-10 - Jeff Rowberg <jeff@rowberg.net>
https://github.com/jrowberg/inmojo-api

================================================================================
The MIT License (MIT)

Copyright (c) 2015 Jeff Rowberg

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

================================================================================
"""

from mechanize import Browser
from BeautifulSoup import BeautifulSoup
from dateutil.parser import parse
import sys, re, datetime, time, urllib, urllib2, cookielib, json, sqlite3

try:
    f = open("credentials.json", "r")
    credentials = json.loads(f.read())
    f.close()
except IOError as e:
    credentials = None
    pass

if credentials == None:
    print("""
Required 'credentials.json' file does not have valid JSON content. Please
create this file with content such as the following:

{
    "inmojo_username": "YOUR_USERNAME",
    "inmojo_password": "YOUR_PASSOWRD"
}
""")
    sys.exit(1)
if credentials['inmojo_username'] == None:
    print("'credentials.json' file does not contain valid username")
    sys.exit(1)
if credentials['inmojo_password'] == None:
    print("'credentials.json' file does not contain valid password")
    sys.exit(1)

inmojo_username = credentials['inmojo_username']
inmojo_password = credentials['inmojo_password']

cj = cookielib.LWPCookieJar()
br = Browser()
br.addheaders = [('User-agent', 'InMojo ScrAPI bridge tool 1.0')]
br.set_cookiejar(cj)
opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))
opener.addheaders.append(('User-agent', 'InMojo SCrAPI bridge tool 1.0'))
try:
    cj.load('inmojo_cookies.txt', ignore_discard=False, ignore_expires=False)
except IOError as e:
    pass
dbfile = "inmojo_%s.db" % inmojo_username
sales_list = []

# check for database
try:
    con = sqlite3.connect(dbfile)
    cur = con.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS sales (number INTEGER PRIMARY KEY, id TEXT, placed INTEGER, updated INTEGER, user TEXT, status TEXT, items INTEGER, total REAL, tracking_number TEXT, tracking_url TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS lines (sale_number INTEGER, item_id TEXT, name TEXT, quantity INTEGER, cost REAL, total REAL)")
except sqlite3.Error:
    # db not available for some reason
    print("Could not open or create '%s' SQLite database for records" % dbfile)

# --------

def cmd_initialize():
    global sales_list
    print("+ Emptying any existing sale data from SQLite database...")
    cur.execute("DELETE FROM sales")
    cur.execute("DELETE FROM lines")
    
    print("+ Attempting to retrieve first page of sales (1-20)...")
    
    html = fetch_autologin()
    cj.save('inmojo_cookies.txt', ignore_discard=False, ignore_expires=False)

    """
    f = open('inmojo_sales_0.html', 'r')
    html = f.read()
    f.close()
    """
    
    offset = 0
    while parse_sales(html):
        offset = offset + 20
        print("+ Retrieving next page of sales (%d-%d)..." % (offset + 1, offset + 20))
        html = fetch_sales_page(offset)

    # reverse order of list since it will be generally in backwards chronological order
    sales_list = sales_list[::-1]

    print("+ Retrieved %d sale entries, adding to SQLite database..." % len(sales_list))
    for sale in sales_list:
        # number, id, placed, updated, user, status, items, total, tracking_number, tracking_url
        cur.execute("INSERT OR IGNORE INTO sales VALUES (%s, '%s', %d, %d, '%s', '%s', %d, %0.2f, '%s', '%s')" % \
            (sale['number'], sale['id'], sale['placed'], sale['updated'], sale['user'], sale['status'], len(sale['items']) - 1, sale['total'], sale['tracking_number'], sale['tracking_url']))
        for item in sale["items"]:
            # sale_number, item_id, name, quantity, cost, total
            cur.execute("INSERT OR IGNORE INTO lines VALUES (%s, '%s', '%s', %d, %0.2f, %0.2f)" % \
                (sale['number'], item['id'], item['name'], item['quantity'], item['cost'], float(item['cost']) * float(item['quantity'])))
        print("+ Added sale %s with %d lines" % (sale['number'], len(sale['items'])))
        
    con.commit()
    
def cmd_update(single_page):
    global sales_list
    print("+ Attempting to retrieve first page of sales (1-20)...")
    
    if single_page == None:
        html = fetch_autologin()
        cj.save('inmojo_cookies.txt', ignore_discard=False, ignore_expires=False)
    else:
        html = single_page

    """
    f = open('inmojo_sales_0.html', 'r')
    html = f.read()
    f.close()
    """
    
    offset = 0
    new_sales_list = []
    updated_sales_list = []
    while True:
        added = 0
        updated = 0
        more = parse_sales(html)
        # check for changes between db and website
        for sale in sales_list[offset:min(20, len(sales_list)-offset)]:
            row = cur.execute("SELECT * FROM sales WHERE number=%s" % sale['number'])
            db_sale = cur.fetchone()
            if db_sale == None:
                # not in database, so add this one
                print("+ Parsed new sale %s" % sale["number"])
                new_sales_list.append(sale)
                added = added + 1
            else:
                # already in database, check status/tracking
                # number, id, placed, updated, user, status, items, total, tracking_number, tracking_url
                if db_sale[5] != sale['status'] or db_sale[8] != sale['tracking_number'] or db_sale[9] != sale['tracking_url']:
                    # something changed, so update this one
                    print("+ Parsed updated sale %s" % sale["number"])
                    updated_sales_list.append(sale)
                    updated = updated + 1
        
        if more and (added > 0 or updated > 0) and single_page == None:
            offset = offset + 20
            print("+ Retrieving next page of sales (%d-%d)..." % (offset + 1, offset + 20))
            html = fetch_sales_page(offset)
        else:
            break

    # reverse order of lists since it will be generally in backwards chronological order
    new_sales_list = new_sales_list[::-1]
    updated_sales_list = updated_sales_list[::-1]

    print("+ Retrieved %d new and %d updated sale entries, updating SQLite database..." % (len(new_sales_list), len(updated_sales_list)))
    for sale in new_sales_list:
        # number, id, placed, updated, user, status, items, total, tracking_number, tracking_url
        cur.execute("INSERT OR IGNORE INTO sales VALUES (%s, '%s', %d, %d, '%s', '%s', %d, %0.2f, '%s', '%s')" % \
            (sale['number'], sale['id'], sale['placed'], sale['updated'], sale['user'], sale['status'], len(sale['items']) - 1, sale['total'], sale['tracking_number'], sale['tracking_url']))
        for item in sale["items"]:
            # sale_number, item_id, name, quantity, cost, total
            cur.execute("INSERT OR IGNORE INTO lines VALUES (%s, '%s', '%s', %d, %0.2f, %0.2f)" % \
                (sale['number'], item['id'], item['name'], item['quantity'], item['cost'], float(item['cost']) * float(item['quantity'])))
        print("+ Added sale %s with %d lines" % (sale['number'], len(sale['items'])))
    for sale in updated_sales_list:
        # number, id, placed, updated, user, status, items, total, tracking_number, tracking_url
        cur.execute("UPDATE sales SET updated=%d, status='%s', tracking_number='%s', tracking_url='%s' WHERE number=%s" % \
            (sale['updated'], sale['status'], sale['tracking_number'], sale['tracking_url'], sale['number']))
        print("+ Updated sale %s with %d lines" % (sale['number'], len(sale['items'])))
    con.commit()
    
def cmd_getsale(number):
    # number, id, placed, updated, user, status, items, total, tracking_number, tracking_url
    cur.execute("SELECT * FROM sales WHERE number='%s'" % number)
    sale_row = cur.fetchone()
    sale = sale_row_to_dict(sale_row)
    print json.dumps(sale)
    
def cmd_getsales(criteria):
    # number, id, placed, updated, user, status, items, total, tracking_number, tracking_url
    where = where_from_criteria(criteria)
    if len(where) > 0:
        cur.execute("SELECT * FROM sales WHERE %s" % ' AND '.join(where))
    else:
        cur.execute("SELECT * FROM sales")
    sale_rows = cur.fetchall()
    sales = []
    for sale_row in sale_rows:
        sales.append(sale_row_to_dict(sale_row))
    print json.dumps(sales)
    
def cmd_getsales_csv(criteria):
    # number, id, placed, updated, user, status, items, total, tracking_number, tracking_url
    where = where_from_criteria(criteria)
    if len(where) > 0:
        cur.execute("SELECT * FROM sales WHERE %s" % ' AND '.join(where))
    else:
        cur.execute("SELECT * FROM sales")
    sales = cur.fetchall()
    
    sales_csv = []
    sales_csv.append('Sale Number,Sale ID,Placed,Updated,User,Status,Items,Total,Tracking Number,Tracking URL')
    for sale in sales:
        sales_csv.append('%s,%s,%d,%d,%s,%s,%d,$%0.2f,%s,%s' % \
            (sale[0], sale[1], sale[2], sale[3], sale[4], sale[5], sale[6], sale[7], sale[8], sale[9]))
    print '\n'.join(sales_csv)
    
def cmd_getlines_csv(criteria):
    # sale_number, item_id, name, quantity, cost, total
    where = where_from_criteria(criteria)
    if len(where) > 0:
        cur.execute("SELECT lines.* FROM sales JOIN lines ON lines.sale_number=sales.number WHERE %s" % ' AND '.join(where))
    else:
        cur.execute("SELECT lines.* FROM sales JOIN lines ON lines.sale_number=sales.number")
    lines = cur.fetchall()

    lines_csv = []
    lines_csv.append('Sale Number,Item ID,Item Name,Quantity,Cost,Total')
    for line in lines:
        lines_csv.append('%s,%s,%s,%d,$%0.2f,$%0.2f' % \
            (line[0], line[1], line[2], line[3], line[4], line[5]))
    print '\n'.join(lines_csv)
    
def cmd_setstatus(args):
    number = args[0]
    status = args[1].lower()
    cur.execute("SELECT * FROM sales WHERE number='%s'" % number)
    sale_row = cur.fetchone()
    valid_status = [ 'new', 'paid', 'shipped', 'canceled' ]
    if sale_row == None:
        print("Sale '%s' not found in database, try 'update' first" % number)
        sys.exit(1)
        
    id = sale_row[1]
    tracking_number = sale_row[8]
    tracking_url = sale_row[9]
        
    if status not in valid_status:
        print("Status '%s' invalid, must be in %s" % (status, valid_status))
        sys.exit(1)
    if status == "shipped" and len(args) != 4:
        print("Status 'shipped' requires tracking number and tracking URL")
        sys.exit(1)
    if status != "shipped" and len(args) != 2:
        print("Status '%s' requires no further arguments" % status)
        sys.exit(1)
        
    if status == "shipped":
        tracking_number = args[2]
        tracking_url = args[3]

    html = fetch_autologin()
    cj.save('inmojo_cookies.txt', ignore_discard=False, ignore_expires=False)
    form_data = urllib.urlencode({ \
        'status': status, \
        'tracking_no': tracking_number, \
        'tracking_url': tracking_url, \
        'act_update': 'save', \
        'order': id
        })
    print("+ Updating status of sale '%s'..." % number)
    resp = opener.open('http://www.inmojo.com/account_sales.html?cat=all&offset=0', form_data)
    html = resp.read()
    cmd_update(html)

def where_from_criteria(criteria):
    where = []
    for condition in criteria:
        parts = condition.split('=', 1)
        if len(parts) < 2:
            print("Invalid condition '%s': must be format 'name=value'" % condition)
            exit(1)
        if parts[0] == "status":
            where.append('status="%s"' % parts[1])
        elif parts[0] == "user":
            where.append('user="%s"' % parts[1])
        elif parts[0] == "beforeunix":
            where.append('placed<%s' % parts[1])
        elif parts[0] == "onafterunix":
            where.append('placed>=%s' % parts[1])
        elif parts[0] == "beforedate":
            where.append('placed<%s' % int(totimestamp(parse(parts[1]))))
        elif parts[0] == "onafterdate":
            where.append('placed>=%s' % int(totimestamp(parse(parts[1]))))
        elif parts[0] == "ubeforeunix":
            where.append('updated<%s' % parts[1])
        elif parts[0] == "uonafterunix":
            where.append('updated>=%s' % parts[1])
        elif parts[0] == "ubeforedate":
            where.append('updated<%s' % int(totimestamp(parse(parts[1]))))
        elif parts[0] == "uonafterdate":
            where.append('updated>=%s' % int(totimestamp(parse(parts[1]))))
    return where
    
def sale_row_to_dict(sale_row):
    sale = {}
    sale['number'] = sale_row[0]
    sale['id'] = sale_row[1]
    sale['placed'] = sale_row[2]
    sale['updated'] = sale_row[3]
    sale['user'] = sale_row[4]
    sale['status'] = sale_row[5]
    sale['total'] = sale_row[7]
    sale['tracking_number'] = sale_row[8]
    sale['tracking_url'] = sale_row[9]
    sale['items'] = []
    cur.execute("SELECT * FROM lines WHERE sale_number='%s'" % sale_row[0])
    line_rows = cur.fetchall()
    for line_row in line_rows:
        # sale_number, item_id, name, quantity, cost, total
        item = {}
        item['id'] = line_row[1]
        item['name'] = line_row[2]
        item['quantity'] = line_row[3]
        item['cost'] = line_row[4]
        item['total'] = line_row[5]
        sale['items'].append(item)
    return sale

def fetch_sales_page(offset):
    response = br.open("http://www.inmojo.com/account_sales.html?cat=all&offset=%d" % offset)
    return response.read()

def fetch_autologin():
    html = fetch_sales_page(0)
    if 'not_loggedin_nav' in html:
        print("- Not logged in, attempting to log in now...")
        br.select_form(nr = 0)
        br.form['username'] = inmojo_username
        br.form['password'] = inmojo_password
        response = br.submit()
        html = response.read()
        if 'not_loggedin_nav' in html:
            print("! Failed, please verify username and password")
            sys.exit(1)
        else:
            print("+ Success, attempting to retrieve first page of sales (1-20)...")
            html = fetch_sales_page(0)
            
    return html

def parse_sales(html):
    soup = BeautifulSoup(html)
    sale_rows = soup.find('div', id="sales").find('table').findAll('tr')
    sales = []
    sale = {}
    for row in sale_rows:
        try:
            if row['class'] == 'order_row':
                sale = {}
                sale['id'] = str(row.find('input', { 'type': 'hidden', 'name': 'order' })['value'])
                sale['number'] = row.find('td', { 'class': 'col_order' }).renderContents()
                sale['placed'] = row.find('td', { 'class': 'col_placed' }).renderContents()
                if 'sec' in sale['placed']:
                    seconds_ago = float(sale['placed'][:sale['placed'].index(' ')])
                    sale['placed'] = int(totimestamp(datetime.datetime.fromtimestamp(time.time() - (seconds_ago))))
                elif 'min' in sale['placed']:
                    minutes_ago = float(sale['placed'][:sale['placed'].index(' ')])
                    sale['placed'] = int(totimestamp(datetime.datetime.fromtimestamp(time.time() - (60*minutes_ago))))
                elif 'hour' in sale['placed']:
                    hours_ago = float(sale['placed'][:sale['placed'].index(' ')])
                    sale['placed'] = int(totimestamp(datetime.datetime.fromtimestamp(time.time() - (60*60*hours_ago))))
                elif 'day' in sale['placed']:
                    days_ago = float(sale['placed'][:sale['placed'].index(' ')])
                    sale['placed'] = int(totimestamp(datetime.datetime.fromtimestamp(time.time() - (60*60*24*days_ago))))
                else:
                    try:
                        sale['placed'] = int(totimestamp(parse(sale['placed'])))
                    except ValueError as e:
                        # "now" or "a moment ago"
                        sale['placed'] = int(totimestamp(datetime.datetime.fromtimestamp(time.time())))
                sale['updated'] = row.find('td', { 'class': 'col_updated' }).renderContents()
                if 'sec' in sale['updated']:
                    seconds_ago = float(sale['updated'][:sale['updated'].index(' ')])
                    sale['updated'] = int(totimestamp(datetime.datetime.fromtimestamp(time.time() - (seconds_ago))))
                elif 'min' in sale['updated']:
                    minutes_ago = float(sale['updated'][:sale['updated'].index(' ')])
                    sale['updated'] = int(totimestamp(datetime.datetime.fromtimestamp(time.time() - (60*minutes_ago))))
                elif 'hour' in sale['updated']:
                    hours_ago = float(sale['updated'][:sale['updated'].index(' ')])
                    sale['updated'] = int(totimestamp(datetime.datetime.fromtimestamp(time.time() - (60*60*hours_ago))))
                elif 'day' in sale['updated']:
                    days_ago = float(sale['updated'][:sale['updated'].index(' ')])
                    sale['updated'] = int(totimestamp(datetime.datetime.fromtimestamp(time.time() - (60*60*24*days_ago))))
                else:
                    try:
                        sale['updated'] = int(totimestamp(parse(sale['updated'])))
                    except ValueError as e:
                        # "now" or "a moment ago"
                        sale['updated'] = int(totimestamp(datetime.datetime.fromtimestamp(time.time())))
                sale['user'] = row.find('td', { 'class': 'col_buyer' }).a.renderContents().lower()
                try:
                    sale['status'] = str(row.find('td', { 'class': 'col_status' }).find('option', selected="selected")['value'])
                except TypeError as e:
                    sale['status'] = row.find('span', { 'class': 'sales_status_text' }).renderContents()
                    if sale['status'].lower() == "pre-order review": sale['status'] = 'review'
                sale['tracking_number'] = str(row.find('td', { 'class': 'col_status' }).find('input', { 'name': "tracking_no" })['value'])
                sale['tracking_url'] = str(row.find('td', { 'class': 'col_status' }).find('input', { 'name': "tracking_url" })['value'])
                sale['items'] = []
                sale['total'] = 0.0
                if sale["tracking_number"] == "None": sale["tracking_number"] = ""
                if sale["tracking_url"] == "None": sale["tracking_url"] = ""
            elif row['class'] == 'order_detail':
                item = {}
                item['name'] = row.find('td', { 'class': 'col_product' }).find(['a', 'span']).renderContents()
                item_link = row.find('td', { 'class': 'col_product' }).find('a')
                item['id'] = ''
                if item_link != None and str(item_link['href'])[0:6] == '/item/':
                        item['id'] = str(item_link['href'])[6:-1]
                item['quantity'] = 1
                item_full = row.find('td', { 'class': 'col_product' }).renderContents().strip()
                matches = re.search('x +([0-9]+)$', item_full, 0)
                if matches != None: item['quantity'] = int(matches.group(1))
                item['cost'] = row.find('td', { 'class': 'col_cost' }).renderContents().strip()
                if item['cost'] == 'FREE':
                    item['cost'] = 0.0
                else:
                    item['cost'] = float(item['cost'][1:]) / item['quantity']
                sale['items'].append(item)
            elif row['class'] == 'total':
                sale['total'] = row.find('td', { 'class': 'col_cost' }).renderContents().strip()
                if sale['total'] == 'FREE':
                    sale['total'] = 0.0
                else:
                    sale['total'] = float(sale['total'][1:])
                sales_list.append(sale)
        except KeyError as e:
            continue

    #f = open('inmojo_sales_%s_%d.json' % (inmojo_username, offset), 'w')
    #f.write(json.dumps(sales))
    #f.close()
    
    # return True if more pages exist, False otherwise
    return 'disable_link' not in str(soup.find('div', { 'class': 'std_sort' }).div.findAll('span')[1])
    
def totimestamp(dt, epoch=datetime.datetime(1970, 1, 1)):
    td = dt - epoch
    # return td.total_seconds()
    return (td.microseconds + (td.seconds + td.days * 24 * 3600) * 10**6) / 1e6 


# check for valid arguments
if len(sys.argv) == 1:
    print('''
inmojo_scrapi.py <command> [arg1 [arg2 [...]]]
    initialize              fetch complete sale history from InMojo
    update                  fetch status of all sales since last update/init
    getsale <sale_num>      output JSON-formatted sale record for given sale
    getsales [criteria]     output JSON-formatted sale/item collection
    getsales_csv [criteria] output CSV-formatted sale list
    getlines_csv [criteria] output CSV-formatted line item list

    CRITERIA:
        status=value                sales with the given status
        user=name                   sales from the given user
        beforeunix=timestamp        sales made before <timestamp>
        onafterunix=timestamp       sales made on or after <timestamp>
        beforedate=YYYY-mm-dd       sales made before <YYYY-mm-dd>
        onafterdate=YYYY-mm-dd      sales made on or after <YYYY-mm-dd>
        ubeforeunix=timestamp       sales updated before <timestamp>
        uonafterunix=timestamp      sales updated on or after <timestamp>
        ubeforedate=YYYY-mm-dd      sales updated before <YYYY-mm-dd>
        uonafterdate=YYYY-mm-dd     sales updated on or after <YYYY-mm-dd>
    
    setstatus <sale_num> <status> [tracking_number tracking_url]
''')
    sys.exit(0)
else:
    command = sys.argv[1].lower()
    if command == "initialize":
        if len(sys.argv) != 2:
            print("Error: 'initialize' command takes no arguments")
            sys.exit(1)
        cmd_initialize()
    elif command == "update":
        if len(sys.argv) != 2:
            print("Error: 'update' command takes no arguments")
            sys.exit(1)
        cmd_update(None)
    elif command == "getsale":
        if len(sys.argv) != 3:
            print("Error: 'getsale' command takes 1 argument")
            sys.exit(1)
        cmd_getsale(sys.argv[2])
    elif command == "getsales":
        cmd_getsales(sys.argv[2:])
    elif command == "getsales_csv":
        cmd_getsales_csv(sys.argv[2:])
    elif command == "getlines_csv":
        cmd_getlines_csv(sys.argv[2:])
    elif command == "setstatus":
        if len(sys.argv) != 4 and len(sys.argv) != 6:
            print("Error: 'setstatus' command takes 2 or 4 arguments")
            sys.exit(1)
        cmd_setstatus(sys.argv[2:])
    else:
        print("Error: '%s' is not a known command" % command)
        sys.exit(1)

sys.exit(0)
