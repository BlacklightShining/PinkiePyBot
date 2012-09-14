#!/usr/bin/env python
'''
head.py - Phenny HTTP Metadata Utilities
Copyright 2008, Sean B. Palmer, inamidst.com
Licensed under the Eiffel Forum License 2.

http://inamidst.com/phenny/

Modified by Jordan Kinsley <jordan@jordantkinsley.org>
'''

import re
import urllib.request
import urllib.parse
import urllib.error
import http.client
import http.cookiejar
import time
from datetime import timedelta
from html.entities import name2codepoint
import web
import lxml.html
try:
    import bs4
    if bs4.__version__ not in ('4.1.2','4.1.3'): # TODO: make this work with possible future versions
        raise ImportError
    from bs4 import BeautifulSoup as Soup
except ImportError:
    print('Can\'t import BeautifulSoup 4.1.2 or greater; we will only be able to get minimal FimFiction.net stats.')
    print('Check your Python path and local packages to make sure BeautifulSoup 4 is installed.')
from tools import deprecated

cj = http.cookiejar.LWPCookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
urllib.request.install_opener(opener)

def head(phenny, input): 
    """Provide HTTP HEAD information."""
    uri = input.group(2)
    uri = (uri or '')
    if ' ' in uri: 
        uri, header = uri.rsplit(' ', 1)
    else: uri, header = uri, None

    if not uri and hasattr(phenny, 'last_seen_uri'): 
        try: uri = phenny.last_seen_uri[input.sender]
        except KeyError: return phenny.say('?')

    if not uri.startswith('htt'): 
        uri = 'http://' + uri
    # uri = uri.replace('#!', '?_escaped_fragment_=')
    
    start = time.time()

    try:
        info = web.head(uri)
        info['status'] = '200'
    except urllib.error.HTTPError as e:
        return phenny.say(str(e.code))
    except http.client.InvalidURL:
        return phenny.say("Not a valid URI, sorry.")
    except IOError:
        return phenny.say("Can't connect to %s" % uri)

    resptime = time.time() - start

    if header is None: 
        data = []
        if 'Status' in info: 
            data.append(info['Status'])
        if 'content-type' in info: 
            data.append(info['content-type'].replace('; charset=', ', '))
        if 'last-modified' in info: 
            modified = info['last-modified']
            modified = time.strptime(modified, '%a, %d %b %Y %H:%M:%S %Z')
            data.append(time.strftime('%Y-%m-%d %H:%M:%S UTC', modified))
        if 'content-length' in info: 
            data.append(info['content-length'] + ' bytes')
        data.append('{0:1.2f} s'.format(resptime))
        phenny.reply(', '.join(data))
    else: 
        headerlower = header.lower()
        if headerlower in info: 
            phenny.say(header + ': ' + info.get(headerlower))
        else: 
            msg = 'There was no %s header in the response.' % header
            phenny.say(msg)
head.commands = ['head']
head.example = '.head http://www.w3.org/'

r_title = re.compile(r'(?ims)<title[^>]*>(.*?)</title\s*>')
r_entity = re.compile(r'&[A-Za-z0-9#]+;')

@deprecated
def f_title(self, origin, match, args): 
    """.title <URI> - Return the title of URI."""
    uri = match.group(2)
    uri = (uri or '')

    if not uri and hasattr(self, 'last_seen_uri'): 
        uri = self.last_seen_uri.get(origin.sender)
    if not uri: 
        return self.msg(origin.sender, 'I need a URI to give the title of...')
    title = gettitle(uri)
    if title:
        self.msg(origin.sender, origin.nick + ': ' + title)
    else: self.msg(origin.sender, origin.nick + ': No title found')
f_title.commands = ['title']

def noteuri(phenny, input): 
    uri = input.group(1)
    if not hasattr(phenny.bot, 'last_seen_uri'): 
        phenny.bot.last_seen_uri = {}
    phenny.bot.last_seen_uri[input.sender] = uri
noteuri.rule = r'.*(http[s]?://[^<> "\x01]+)[,.]?'
noteuri.priority = 'low'

titlecommands = r'(?:' + r'|'.join(f_title.commands) + r')'
def snarfuri(phenny, input):
    if re.match(r'(?i)' + phenny.config.prefix + titlecommands, input.group()):
        return
    uri = input.group(1)
    title = gettitle(uri)
    if title:
        phenny.msg(input.sender, '[ ' + title + ' ]')
snarfuri.rule = r'.*(http[s]?://[^<> "\x01]+)[,.]?'
snarfuri.priority = 'low'

def gettitle(uri):
    if not ':' in uri: 
        uri = 'http://' + uri
    uri = uri.replace('#!', '?_escaped_fragment_=')

    title = None
    localhost = [
        'http://localhost/', 'http://localhost:80/', 
        'http://localhost:8080/', 'http://127.0.0.1/', 
        'http://127.0.0.1:80/', 'http://127.0.0.1:8080/', 
        'https://localhost/', 'https://localhost:80/', 
        'https://localhost:8080/', 'https://127.0.0.1/', 
        'https://127.0.0.1:80/', 'https://127.0.0.1:8080/', 
    ]
    for s in localhost: 
        if uri.startswith(s): 
            return phenny.reply('Sorry, access forbidden.')
    
    youtube = re.compile('http(s)?://(www.)?youtu(.be|be.)(com|co.uk|ca)?/')
    if youtube.match(uri):
        return get_youtube_title(uri)
    
    fimfiction = re.compile('http(s)?://(www.)?fimfiction.net/story/')
    if fimfiction.match(uri):
        return get_story_title(uri)
    
    try: 
        redirects = 0
        while True: 
            info = web.head(uri)

            if not isinstance(info, list): 
                status = '200'
            else: 
                status = str(info[1])
                info = info[0]
            if status.startswith('3'): 
                uri = urllib.parse.urljoin(uri, info['Location'])
            else: break

            redirects += 1
            if redirects >= 25: 
                return None

        try: mtype = info['content-type']
        except: 
            return None

        if not (('/html' in mtype) or ('/xhtml' in mtype)): 
            return None

        bytes = web.get(uri)
        #bytes = u.read(262144)
        #u.close()

    except IOError: 
        return

    m = r_title.search(bytes)
    if m: 
        title = m.group(1)
        title = title.strip()
        title = title.replace('\t', ' ')
        title = title.replace('\r', ' ')
        title = title.replace('\n', ' ')
        while '  ' in title: 
            title = title.replace('  ', ' ')
        if len(title) > 200: 
            title = title[:200] + '[...]'
        
        def e(m): 
            entity = m.group(0)
            if entity.startswith('&#x'): 
                cp = int(entity[3:-1], 16)
                return chr(cp)
            elif entity.startswith('&#'): 
                cp = int(entity[2:-1])
                return chr(cp)
            else: 
                char = name2codepoint[entity[1:-1]]
                return chr(char)
        title = r_entity.sub(e, title)

        if title: 
            title = title.replace('\n', '')
            title = title.replace('\r', '')
        else: title = None
    return title
    
def query(vid):
    ''' returns the title, viewcount, time, and uploader of a Youtube video. vid is the Youtube video ID at the end of the Youtube URL.'''
    main = 'http://gdata.youtube.com/feeds/api/videos/'
    ext = '?v=2&alt=jsonc'
    conn = urllib.request.urlopen(main + vid + ext)
    html = str(conn.read()) # We just a bunch of bytes and we need a string for the following operations.
    # We seem to have received a JSON response to our request. Using the standard library to decode JSON
    # just results in a string, so we're going to just not bother with it today.
    # For each of the following operations, we are:
    # 1. splitting the string in half at the first split operation;
    # 2. taking the second half of the string;
    # 3. splitting the string again at the first comma;
    # 4. taking the first result of the now split string
    title = html.split('"title":')[1].split(',')[0].strip('"')
    uploader = html.split('"uploader":')[1].split(',')[0].strip('"')
    viewcount = html.split('"viewCount":')[1].split(',')[0]
    duration = html.split('"duration":')[1].split(',')[0]
    likes = html.split('"likeCount":')[1].split(',')[0].strip('"')
    ratings = html.split('"ratingCount":')[1].split(',')[0]
    time = str(timedelta(seconds=int(duration)))
    return title, viewcount, time, uploader, likes, ratings

def get_youtube_title(uri):
    vid = None
    if 'youtu.be' in uri:
        vid = uri[uri.rindex('/'):]
    else:
        if '?v=' in uri:
            vid = uri[uri.index('?v=')+3:uri.index('?v=') + 14]
        elif '&v=' in uri:
            vid = uri[uri.index('&v=')+3:uri.index('&v=') + 14]
        else:
            raise GrumbleError('That\'s not a fucking correct Youtube URL!')
    title, views, time, uploader, likes, ratings = query(vid)
    percentage = str(round((float(likes) / float(ratings)) * 100,2))
    # Not including the uploader in the title info; it's rarely important in determining a link's quality.
    return title + " - " + views + " views - " + time + " long - " + likes + " likes - " + percentage + "%"

    
def get_story_title(uri):
    # TODO: get word count, views, categories
    # Word count can't be found by lxml.html
    # Views can't be found by lxml.html
    # Categories can't be found by lxml.html
    raw_page = web.get(uri)
    story_page = lxml.html.fromstring(raw_page)
    likes = story_page.find_class('likes')[0].text_content()
    dislikes = story_page.find_class('dislikes')[0].text_content()
    percentage = (float(likes) / (float(dislikes) + float(likes))) * 100
    percentage = str(round(percentage, 2))
    author = story_page.find_class('name name_author')[0].text_content().strip()
    head = story_page.head.text_content()
    story = head[0:head.index('-')].rstrip()
    
    views = None
    categories = []
    word_count = None
    chapters = None
    
    if Soup:
        soup = Soup(raw_page)
        categories = soup.find_all(class_='story_category')
        views = soup.find(class_='views').get_text().strip()
        views = views[:views.index('(')].strip()
        wc = soup.find_all(class_='word_count')
        word_count = wc[len(wc) - 1].get_text().strip()
        chapters = len(soup.find_all(class_='chapter_link'))
    title = story + " by " + author
    
    if chapters:
        title = title + ' - ' + str(chapters)
        if chapters > 1:
            title = title + ' chapters'
        else:
            title = title + ' chapter'
    if views:
        title = title + " - " + views + " views"
    if len(categories) > 0:
        str_categories = ""
        # each category is a Tag; we need to use get_text to get the actual category name
        for category in categories:
            str_categories = str_categories + "[" + category.get_text() + "]"
        title = title + " - " + str_categories
    if word_count:
        title = title + ' - ' + word_count
    
    title = title + " - Likes: " + likes + " - Dislikes: " + dislikes + " - " + percentage + "%"
    return title

if __name__ == '__main__': 
    print(__doc__.strip())
