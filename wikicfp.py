import getopt
import re
import requests
import sys
from bs4 import BeautifulSoup
from urllib.parse import urlencode, parse_qs


class WikiCFP:
  FIELD_STATUS = 'status'
  FIELD_REASON = 'reason'
  FIELD_EVENTS = 'events'
  FIELD_ID = 'id'
  FIELD_CONF_NAME = 'conf_name'
  FIELD_EVENT_NAME = 'event_name'
  FIELD_WHEN = 'when'
  FIELD_WHERE = 'where'
  FIELD_DEADLINE = 'deadline'
  FIELD_URL = 'url'

  STATUS_FAIL = 'FAIL'
  STATUS_OK = 'OK'

  BASE_URL = 'http://www.wikicfp.com'
  SERIES_PATH = 'cfp/series'
  PROGRAM_PATH = 'cfp/program'
  EVENT_PATH = 'cfp/servlet/event.showcfp'
  SEARCH_PATH = 'cfp/servlet/tool.search'
  
  def _fail(self, reason):
    return {
      self.FIELD_STATUS: self.STATUS_FAIL,
      self.FIELD_REASON: reason
    }

  def _ok(self, events_list):
    return {
      self.FIELD_STATUS: self.STATUS_OK,
      self.FIELD_EVENTS: events_list
    }

  def _make_event_obj(self, _id, conf_name, event_name, when, where, deadline, url):
    return {
      self.FIELD_ID: _id,
      self.FIELD_CONF_NAME: conf_name,
      self.FIELD_EVENT_NAME: event_name,
      self.FIELD_WHEN: when,
      self.FIELD_WHERE: where,
      self.FIELD_DEADLINE: deadline,
      self.FIELD_URL: url
    }

  def get_info_by_search(self, keyword):
    
    params = {'q': keyword, 'year': 'f'}
    url = '{}/{}?{}'.format(self.BASE_URL, self.SEARCH_PATH, urlencode(params))
    
    r = requests.get(url)
    html = BeautifulSoup(r.text, 'lxml')
    
    all_tables = html.find_all('table')
    if not all_tables or len(all_tables) < 2:
      return self._fail('Unable to find information.')
    
    events_url = []
    for a in all_tables[2].find_all('a'):
      if self.EVENT_PATH in a['href']:
        events_url.append('{}{}'.format(self.BASE_URL, a['href']))

    if not events_url:
      return self._fail('Unable to find events.')
    
    events_list = []
    for event_url in events_url:
      r = self.get_info_by_event(event_url)
      if r['status'] == self.STATUS_OK:
        events_list += r[self.FIELD_EVENTS]

    return self._ok(events_list)
    

  def get_info_by_event(self, event_url):

    endpoint_url = '{}/{}'.format(self.BASE_URL, self.EVENT_PATH)
    if not event_url or endpoint_url not in event_url:
      return self._fail('URL invalid.')
    
    params = parse_qs(event_url.split('?')[1])
    _id = params['eventid'][0]
    r = requests.get(event_url)

    columns = []
    values = []

    html = BeautifulSoup(r.text, 'lxml')

    title = html.find('span', {'property': 'v:description'})
    if not title:
      return self._fail('Unable to find information.')

    all_tables = html.find_all('table')
    if not all_tables and len(all_tables) < 2:
      return self._fail('Unable to find information.')

    header_table = all_tables[2]
    if not header_table and len(header_table) < 3:
      return self._fail('Unable to find information.')

    generic_info_table = header_table.find_all('table')[3]
    if not generic_info_table and len(generic_info_table) < 3:
      return self._fail('Unable to find information.')

    if not generic_info_table:
      return self._fail('Unable to find information.')

    info_table = generic_info_table.find('table')

    for col in info_table.find_all('th'):
      columns.append(col.string.strip())

    for info in info_table.find('table'):
      if not info: continue
      content = info.find('td')
      if content != -1:
        values.append(content.get_text().strip())

    if len(values) != len(columns):
      return self._fail('Unable to find information.')
    
    event_name = title.string.strip()
    conf_name = event_name.split(':')[0].strip()
    when, where, deadline = None, None, None
    for c, v in zip(columns, values):
      if 'When' in c:
        when = v
      elif 'Where' in c:
        where = v
      elif 'Deadline' in c:
        deadline = v

    event_list = [self._make_event_obj(_id, conf_name, event_name, 
                                       when, where, deadline, event_url)]

    return self._ok(event_list)


  def get_info_by_series(self, series_name):

    if not series_name:
      return self._fail('Conference name is invalid.')

    first_letter = series_name[0].upper()
    params = {'t': 'c', 'i': first_letter}
    url = '{}/{}?{}'.format(self.BASE_URL, self.SERIES_PATH, urlencode(params))
    
    r = requests.get(url)
    html = BeautifulSoup(r.text, 'lxml')
    all_tables = html.find_all('table')
    
    if not all_tables or len(all_tables) != 7:
      return self._fail('Unable to locate content.')
    
    events_url = []
    for a in all_tables[2].find_all('a'):
      _, params_str = a['href'].split('?')
      params = parse_qs(params_str)

      if 's' in params and params['s'][0] == series_name:
        _params = {'id': params['id'][0]}
        series_url = '{}/{}?{}'.format(self.BASE_URL, 
                                       self.PROGRAM_PATH, urlencode(_params))
        events_url += self._get_events_from_series(series_url)

    if not events_url:
      return self._fail('Unable to find events.')
    
    events_list = []
    for event_url in events_url:
      r = self.get_info_by_event(event_url)
      if r[self.FIELD_STATUS] == self.STATUS_OK:
        events_list += r[self.FIELD_EVENTS]
    
    return self._ok(events_list)


  def _get_events_from_series(self, series_url):
    r = requests.get(series_url)
    html = BeautifulSoup(r.text, 'lxml')
    
    all_tables = html.find_all('table')
    if not all_tables and len(all_tables) < 2:
      return self._fail('Unable to find information.')
    
    events_url = []
    for a in all_tables[2].find_all('a'):
      if self.EVENT_PATH in a['href']:
        events_url.append('{}{}'.format(self.BASE_URL, a['href']))

    return events_url

class Config:
  search = None
  conference = None
  event_url = None
  show_help = False

def parse_args(args):
  shortopts = 's:c:e:h'
  
  longopts = [
    'search=',
    'conference=',
    'event_url=',
    'help'
  ]

  config = Config()
  options, _ = getopt.getopt(sys.argv[1:], shortopts, longopts)

  for opt, arg in options:
    if opt in ('-s', '--search'):
      config.search = arg
    elif opt in ('-c', '--conference'):
      config.conference = arg
    elif opt in ('-e', '--event-url'):
      config.event_url = arg
    elif opt in ('-h', '--help'):
      config.show_help = True

  return config


def print_help():
    print("""WikiCFP - http://wikicfp.com
Usage:
    python wikicfp.py --search [KEYWORD]
    python wikicfp.py --conference [SERIES_NAME]
    python wikicfp.py --event-url [URL]
Options:
    -s --search=KEYWORD         Search by keyword
    -c --conference=SERIES_NAME Search by series name
    -e --event_url=URL          Collect event information
    -h --help                   Print this message
    """)

if __name__ == '__main__':
  if len(sys.argv) <= 1:
    print('Missing arguments')
    sys.exit(1)

  config = parse_args(sys.argv[1:])

  if config.show_help:
    print_help()
    sys.exit(0)

  wikicfp = WikiCFP()

  r = {}
  if config.search:
    r = wikicfp.get_info_by_search(config.search)
  elif config.conference:
    r = wikicfp.get_info_by_series(config.conference)
  elif config.event_url:
    r = wikicfp.get_info_by_event(config.event_url)

  
  if WikiCFP.STATUS_FAIL == r[WikiCFP.FIELD_STATUS]:
    print('Not found.')
  else:
    for e in r[WikiCFP.FIELD_EVENTS]:
      print('Event: {}'.format(e[WikiCFP.FIELD_CONF_NAME]))
      print('When: {}'.format(e[WikiCFP.FIELD_WHEN]))
      print('Where: {}'.format(e[WikiCFP.FIELD_WHERE]))
      print('Deadline: {}'.format(e[WikiCFP.FIELD_DEADLINE]))
      print('URL: {}'.format(e[WikiCFP.FIELD_URL]))
      print('')
