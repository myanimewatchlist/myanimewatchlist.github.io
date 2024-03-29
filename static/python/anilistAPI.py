import hashlib
import json
import os
import sys
import time
import traceback
from datetime import datetime

sys.setrecursionlimit(10**12)

try:
    from browser import ajax
    from browser import self as window
    WEB = True
    CACHE = 0
except:
    import requests
    WEB = False
    CACHE = 0

CWD: str = 'blob:http://'
TMP_CACHE: dict = {}
CUSTOM: list = []
MANGA: bool = False


class Graphql:
    def __init__(self):
        def allowed_string_format(string): return [i.strip(
        ) for i in string.strip().splitlines() if not i.strip().startswith('-')]
        self.AllowedRelations = allowed_string_format('''
            ADAPTATION
            PREQUEL
            SEQUEL
            PARENT
            SIDE_STORY
            -CHARACTER
            SUMMARY
            ALTERNATIVE
            SPIN_OFF
            -OTHER
            SOURCE
            COMPILATION
            CONTAINS
        ''')

        self.AllowedFormats = allowed_string_format('''
            TV
            MOVIE
            TV_SHORT
            OVA
            ONA
            SPECIAL
            MUSIC
            -MANGA
            -NOVEL
            -ONE_SHOT
        ''')
        if MANGA:
            self.AllowedFormats = ['MANGA', 'NOVEL', 'ONE_SHOT']

        self.AllowedStatus = allowed_string_format('''
            FINISHED
            RELEASING
            -NOT_YET_RELEASED
            -CANCELLED
            HIATUS
        ''')

        self.cache = {}
        self.extension = '.graphql'
        self.database = os.path.join(CWD, 'static', 'graphql')

    def query(self, name: str) -> str:
        name = name.replace(' ', '_').upper()
        if name in self.cache:
            return self.cache[name]
        path = os.path.join(self.database, name + self.extension)
        with open(path, 'r') as qf:
            qd = qf.read()
            self.cache[name] = qd
            return qd

    def request_cache(self, query, variables):
        cache_name = hashlib.md5(
            ''.join(
                [query] + [str(value) + str(key)
                           for key, value in variables.items()]
            ).encode()
        ).hexdigest()
        cache_file = os.path.join(CWD, '.cache', cache_name + '.json')

        if CACHE <= 0 and WEB:
            return False, cache_name
        elif CACHE <= 0:
            return False, cache_file

        if WEB:
            if f'{cache_name}.time' in TMP_CACHE:
                if (time.time() - float(TMP_CACHE[f'{cache_name}.time'].replace('"', ''))) > CACHE:
                    return False, cache_name
                return json.loads(TMP_CACHE[f'{cache_name}.data']), None
            else:
                return False, cache_name
        else:
            if not os.path.isdir(os.path.join(CWD, '.cache')):
                os.mkdir(os.path.join(CWD, '.cache'))
            if os.path.exists(cache_file):
                cache = json.load(open(cache_file))
                if (time.time() - cache['time']) > CACHE:
                    return False, cache_file
                return cache['response'], None
            else:
                return False, cache_file

    def request(self, query, **var):
        global TMP_CACHE

        query = self.query(query)
        cache, cache_iD = self.request_cache(query, var)
        if cache and CACHE >= 1:
            return cache

        if len(API_KEY) != 0:
            headers = {
                'Authorization': 'Bearer ' + API_KEY,
            }
        else:
            headers = {}

        if WEB:
            tempResponse = []
            _ = ajax.post(
                'https://graphql.anilist.co',
                blocking=True,
                mode="json",
                headers=headers,
                data={
                    'query': query,
                    'variables': json.dumps(var),
                },
                oncomplete=tempResponse.append
            )
            response = tempResponse[-1].json
            if 'errors' not in response and CACHE >= 1 and response['data'] is not None and CACHE != 0:
                TMP_CACHE[f'{cache_iD}.time'] = time.time()
                TMP_CACHE[f'{cache_iD}.data'] = str(response)
            return response
        else:
            response = requests.post(
                'https://graphql.anilist.co',
                headers=headers,
                json={
                    'query': query,
                    'variables': var,
                },
            ).json()
            if 'errors' not in response and CACHE >= 1 and response['data'] is not None:
                json.dump({'time': time.time(), 'response': response},
                          open(str(cache_iD), 'w'), indent=4)
            return response

    def GET(self, query, **variables):
        response = self.request(query, **variables)
        watchedRaw = []
        stopped_watching = []
        watched = {}

        if 'errors' in response:
            if WEB:
                window.send(
                    json.dumps({
                        'ERROR': json.dumps(response)
                    })
                )
            return response, None, None
        
        completed_status = ('COMPLETED', 'REPEATING')
        uncompleted_stats = ('CURRENT', 'DROPPED', 'PAUSED')
        
        for al in response['data']['MediaListCollection']['lists']:
            if al['status'] in completed_status:
                watchedRaw.extend([media for media in al['entries'] if media['media']['format'] in self.AllowedFormats])

        for al in response['data']['MediaListCollection']['lists']:
            if al['status'] in uncompleted_stats:
                stopped_watching.extend([media['media']['id']
                                        for media in al['entries']
                                        if media['media']['format'] in self.AllowedRelations
                                        ])

        for media in watchedRaw:
            media = media['media']
            watched[media['id']] = {
                'id': media['id'],
                'format': media['format'],
                'relations': [
                    {
                        'id': node['node']['id'],
                        'format': node['node']['format'],
                    } for node in media['relations']['edges']
                    if node['relationType']
                    in self.AllowedRelations
                    and node['node']['format']
                    in self.AllowedFormats
                ]
            }
        return watched, response['data']['MediaListCollection']['user'], stopped_watching


class Tree:
    def __init__(self):
        self.record = []
        self.gql = Graphql()
        self.completed = False
        self.processData = []

    def request_list(self, db):
        if not len(db) == 0:
            rqlist = sum([db] if isinstance(db[-1], int) else db, [])
        else:
            rqlist = []
            
        self.record.append(rqlist)
        lastPage = True
        currentPage = 0
        outList = []
        while lastPage:
            currentPage += 1
            rawList = self.gql.request(
                'anime relations', animeList=rqlist, page=currentPage)
            outList.extend(
                [
                    [iD['id']] + [
                        rId['node']['id'] for rId in iD['relations']['edges']
                        if rId['relationType']
                        in self.gql.AllowedRelations
                        and rId['node']['format']
                        in self.gql.AllowedFormats
                    ]
                    for iD in rawList['data']['Page']['media']
                ]
            )
            lastPage = rawList['data']['Page']['pageInfo']['hasNextPage']
        self.processData.append(outList)
        return outList

    def next_db(self, res):
        db = list(set(sum(res, [])) - set(sum(self.record, [])))
        if len(db):
            return db
        else:
            self.completed = True

    def get_tree(self, start, flat=False):
        if not flat:
            db = [[key] + [iD['id'] for iD in value['relations']]
                for key, value in start.items()]
        else:
            db = start
        
        self.processData.append(db)
        
        while not self.completed:
            res = self.request_list(db)
            db = self.next_db(res)
            
        return self.processData


class Relations:
    def __init__(self):
        self.tree = Tree()
        
    def process(self, data):
        flat_data = list(sum(data, []))
        custom_index = []
        cdm = self.custom_data_map()
        
        flat_out_data = list(sum(flat_data, []))
        for custom_i in list(sum(CUSTOM, [])):
            if custom_i in flat_out_data:
                custom_index.append(cdm[custom_i])
        common = [CUSTOM[i] for i in list(set(custom_index))] 
        
        if len(common) != 0:
            common_relations = self.tree.get_tree(common, flat=True)
            flat_data.extend(common_relations[-1])
            flat_data.extend(CUSTOM)
        
        return self.remove_similar(flat_data)
    
    def custom_data_map(self):
        out = {}
        for i,v in enumerate(CUSTOM):
            for n in v:
                out[n] = i
        return out
        
    def remove_similar(self, data):
        target_idx = 0
        while target_idx < len(data):
            src_idx = target_idx + 1
            did_merge = False
            while src_idx < len(data):
                if set(data[target_idx]) & set(data[src_idx]):
                    data[target_idx].extend(data[src_idx])
                    data.pop(src_idx)
                    did_merge = True
                    continue
                src_idx += 1
            if not did_merge:
                target_idx += 1
        data = list(map(list, map(set, data)))
        return data


class Processor:
    def __init__(self):
        self.cache = {}
        self.gql = Graphql()
        self.abbreviation = {
            'TV': 'S',
            'TV_SHORT': 'SHORT',
            'SPECIAL': 'SPE',
            'ONE_SHOT': 'PILOT',
            'NOVEL': 'LN',
        }
        self.stat_norm = lambda stat: '-'.join(
            [self.abbreviation.get(k, k) + str(v) for k, v in stat.items()])

    def build_cache(self, data):
        flat_data = sum(data, [])
        lastPage = True
        currentPage = 0
        while lastPage:
            currentPage += 1
            rawList = self.gql.request(
                'anime info', animeList=flat_data, page=currentPage)
            for entry in rawList['data']['Page']['media']:
                self.cache[entry['id']] = entry
            lastPage = rawList['data']['Page']['pageInfo']['hasNextPage']

    def get_first_of_series(self, entry):
        sort = sorted(entry, key=self.series_sort_func)
        default_iD = sort[0]
        for iD in sort:
            if self.cache[iD]['format'] == ('TV' if not MANGA else 'NOVEL'):
                return iD, sort
        return default_iD, sort

    def series_sort_func(self, entry_id):
        mediaDate = self.cache[entry_id]['startDate']
        try:
            return time.mktime(datetime(
                mediaDate['year'],
                mediaDate['month'],
                mediaDate['day'],
            ).timetuple())
        except:
            return float('inf')

    def display_format(self, iD):
        media = self.cache[iD]
        available = media['status'] in self.gql.AllowedStatus
        return {
            'id': media['id'],
            'watched': media['id'] in self.watched,
            'format': media['format'],
            'title': media['title']['english'] if media['title']['english'] else media['title']['romaji'],
            'status': media['status'],
            'available': available,
            'cover': media['coverImage']['large'],
            'url': media['siteUrl'],
            'willWatch': False if (available and media['id'] in self.stopped_watching) else available,
        }

    def unwatch_stat(self, data: dict):
        DROPPED = 0
        NOTRELEASED = 0
        AIRING = 0
        WILLWATCH = 0

        for series in data.values():
            for media in series.values():
                if not media['watched']:
                    if media['status'] in ('RELEASING', 'HIATUS'):
                        AIRING += 1
                    elif media['willWatch']:
                        WILLWATCH += 1
                    elif media['available']:
                        DROPPED += 1
                    else:
                        NOTRELEASED += 1
        return {
            'dropped': DROPPED,
            'notReleased': NOTRELEASED,
            'airing': AIRING,
            'willWatch': WILLWATCH,
            'total': DROPPED + NOTRELEASED + AIRING + WILLWATCH,
        }

    def get_stat(self, items):
        stat = {}
        for formats in self.gql.AllowedFormats:
            count = 0
            for watched_item in items:
                if items[watched_item]['format'] == formats and items[watched_item]['watched']:
                    count += 1
            if count:
                stat[formats] = count
        return stat

    def process_extra_data(self, iD, data):
        out = {}
        out['stat'] = (lambda stat: {'formated': self.stat_norm(
            stat), 'raw': stat})(self.get_stat(data))
        out['totalCount'] = len(data)
        out['watchedCount'] = len([i for i in data if data[i]['watched']])
        out['completed'] = out['totalCount'] == out['watchedCount']
        out['available'] = any([data[i]['available'] for i in data])
        out['outThere'] = all([data[i]['available'] for i in data])
        out['willWatch'] = any(
            [i not in self.stopped_watching for i in data if data[i]['available']])
        return out

    def display_data(self, data, watched, stopped):
        out = {}
        self.watched = watched
        self.stopped_watching = watched + stopped
        self.build_cache(data)
        for collection in data:
            first_iD, release_sort = self.get_first_of_series(collection)
            out[first_iD] = {
                iD: self.display_format(iD)
                for iD in release_sort
            }
            out[first_iD][first_iD]['extra'] = self.process_extra_data(
                first_iD, out[first_iD])
        return out


def data_handler_builder(user):
    global MANGA
    
    MANGA = False
    
    graphql, tree_gen, relation_gen, text_process = Graphql(), Tree(), Relations(), Processor() 
    if isinstance(user, int):
        user = graphql.request('user', userId=user)['data']['User']['name']
    anime_out, user_info, stopped = graphql.GET('user lists', userName=user, type='ANIME')
    if user_info is None:
        return anime_out, False
    tree_out = tree_gen.get_tree(anime_out)
    proc_out = relation_gen.process(tree_out)
    anime_proc = text_process.display_data(proc_out, list(anime_out), stopped)
    
    MANGA = True
    
    graphql, tree_gen, relation_gen, text_process = Graphql(), Tree(), Relations(), Processor()
    manga_out, user_info, stopped = graphql.GET('user lists', userName=user, type='MANGA')
    if user_info is None:
        return anime_out, False
    tree_out = tree_gen.get_tree(manga_out)
    proc_out = relation_gen.process(tree_out)
    manga_proc = text_process.display_data(proc_out, list(manga_out), stopped)
    
    MANGA = False
    
    return {
        'user_info': user_info,
        'anime_proc': anime_proc,
        'manga_proc': manga_proc
    }

def GetUserInfo(user):
    data = data_handler_builder(user)
    
    user_info = data['user_info']
    anime_proc = data['anime_proc']
    manga_proc = data['manga_proc']
    
    text_process = Processor()
    output = {}
    output['USER'] = {
        'id': user_info['id'],
        'name': user_info['name'],
        'url': user_info['siteUrl'],
        'avatar': user_info['avatar']['large'],
        'count': {
            'anime': len(anime_proc),
            'manga': len(manga_proc),
            'unwatch': text_process.unwatch_stat(anime_proc),
            'unread': text_process.unwatch_stat(manga_proc),
            'title': user_info['statistics']['anime']['count'],
            'headings': user_info['statistics']['manga']['count'],
            'episode': user_info['statistics']['anime']['episodesWatched'],
            'chapter': user_info['statistics']['manga']['chaptersRead'],
            'watchtime': (lambda min: {'formated': str(round(min / (60 if min < (24 * 60) else 60 * 24), 1)) + (" Hour's" if min < (24 * 60) else " Day's"), 'raw': min})(user_info["statistics"]["anime"]["minutesWatched"]),
            'readtime': (lambda min: {'formated': str(round(min / (60 if min < (24 * 60) else 60 * 24), 1)) + (" Hour's" if min < (24 * 60) else " Day's"), 'raw': min})(5.6 * user_info['statistics']['manga']['chaptersRead']),
        },
    }
    output['DATA'] = {
        'ANIME': anime_proc,
        'MANGA': manga_proc
    }
    output['CACHE'] = TMP_CACHE
    output['CARD'] = {
        'UserId': output['USER']['id'],
        'UserName': output['USER']['name'],
        'UserSiteUrl': output['USER']['url'],
        'UserAvatar': output['USER']['avatar'],
        'UserAvatarB64': None,
        'AnimeWatched': output['USER']['count']['anime'],
        'MangaRead': output['USER']['count']['manga'],
        'TitleWatched': output['USER']['count']['title'],
        'TitleRead': output['USER']['count']['headings'],
        'EpisodeWatched': output['USER']['count']['episode'],
        'ChaptersRead': output['USER']['count']['chapter'],
        'MinutesWatched': output['USER']['count']['watchtime']['raw'],
        'MinutesRead': output['USER']['count']['readtime']['raw'],
        'WatchTime': output['USER']['count']['watchtime']['formated'],
        'ReadTime': output['USER']['count']['readtime']['formated'],
        'UnwatchDropped': output['USER']['count']['unwatch']['dropped'],
        'UnReadDropped': output['USER']['count']['unread']['dropped'],
        'UnwatchNotReleased': output['USER']['count']['unwatch']['notReleased'],
        'UnReadNotReleased': output['USER']['count']['unread']['notReleased'],
        'UnwatchAiring': output['USER']['count']['unwatch']['airing'],
        'UnReadAiring': output['USER']['count']['unread']['airing'],
        'UnwatchPlausible': output['USER']['count']['unwatch']['willWatch'],
        'UnReadPlausible': output['USER']['count']['unread']['willWatch'],
        'TotalUnwatch': output['USER']['count']['unwatch']['total'],
        'TotalUnRead': output['USER']['count']['unread']['total'],
        'LastUpdateTimestamp': time.time(),
    }
    output['CUSTOM'] = CUSTOM
    return output, True


def main(event):
    global CWD, TMP_CACHE, API_KEY, CUSTOM
    if hasattr(event, 'data'):
        event_data = json.loads(event.data)
        user, CWD, TMP_CACHE, API_KEY, CUSTOM = event_data['user'], event_data['CWD'], event_data['CACHE'], event_data['KEY'], event_data['CUSTOM']
    else:
        user, CWD, API_KEY = event, os.getcwd() + '', ''

    if WEB:
        try:
            data, send = GetUserInfo(user)
            if send:
                window.send(json.dumps(data))
        except Exception as exception:
            error = traceback.format_exc()
            window.send(json.dumps({'ERROR': error}))
    else:
        return GetUserInfo(user)[0]


if WEB:
    window.bind("message", main)
