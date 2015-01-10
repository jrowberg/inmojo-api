## InMojo API

[InMojo](http://www.inmojo.com) is an excellent sales platform for open-source hardware products. However, it is missing an official API to automate order and customer management. I am hopeful that this will change and more than willing to contribute my own efforts to make it happen, but in the meantime, I've put together a Python script that uses [mechanize](https://pypi.python.org/pypi/mechanize) and [BeautifulSoup](https://pypi.python.org/pypi/beautifulsoup4) with a few other Python modules to scrape order data directly from the website into a more API-friendly SQLite database. You can also update orders with new status, tracking number, and tracking URL.

Here's the syntax help from running the script with no arguments:

```
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
```

### Installation and Use

Using the script is pretty simple.

1. Download `inmojo_scrapi.py` and `credentials.json` OR clone the repo
2. Update `credentials.json` with your InMojo username and password
3. Install Python 2.7.x if you don't already have it
4. Use Python's "easy_install" setup tool to install:
    - mechanize
    - BeautifulSoup
    - python-dateutil
5. Run `inmojo_scrapi.py initialize` to get all existing sale records in your account so far
6. Run `inmojo_scrapi.py update` from time to time to get all new or updated sale records
7. Use the various *get* commands as desired to help integrate with any other tools you use

Output in JSON format give you a structured list where each sale records includes items as a sub-object. The CSV output is broken apart into either a sale list or a line item detail list (line items include order numbers for correlating data later).

### "ScrAPI" Limitations

There are certain things that are simply not possible from scraping the website, due to the fact that the information just isn't there. For example:

- There is no shipping address data available
- There is no correlated PayPal payment data available

These things are sent to sellers via email only, and (oddly) they are not accessible through the web interface later.

Also, there are many things that this script *could* do which it does not, such as getting or setting inventory amounts, listing, adding, or updating actual items or variants for sale, and so on. I did not add support for these things because they fall outside of te category of things that I really need to automate (namely, order management).

More features may be added in the future, but hopefully the site will icorporate an official API before then. Scraping web content isn't exactly ideal.

Until then, happy selling!
