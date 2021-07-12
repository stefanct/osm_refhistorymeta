from OSMPythonTools.overpass import Overpass
import logging
import os
import re
import sys
import time
import urllib

QUERY_TIMEOUT = 3*60 # in seconds
TOO_MANY_REQUESTS_WAIT = 2*60 # in seconds
MAX_WAY_VERSION_PRODUCT = QUERY_TIMEOUT*16000 # skip relations having more than this versions^1.5 × ways

# Python is stupid (re. pipes)
sys.stdout.reconfigure(line_buffering=True)

def query_cur_meta(id):
  return f'''
rel({id})->.r;
(way(r.r);)->.ways;

make stat version=r.u(version()),
timestamp=r.u(timestamp()),
user=r.u(user()),
changeset=r.u(changeset()),
waycount=ways.count(ways);
out;
'''

def query_hist_meta(id):
  return f'''
timeline(relation,{id});
for (t["created"])\u007b
  retro(_.val)
  \u007b
    rel({id});
    make stat version=u(version()),
      timestamp=u(timestamp()),
      user=u(user()),
      changeset=u(changeset()),
      ;
    out;
  \u007d
\u007d
'''

def main():
  overpass = Overpass()
  logger = logging.getLogger('OSMPythonTools')
  logger.setLevel(logging.ERROR)

  regex = re.compile(r"(\d+)")

  users = {}
  creators = {}

  try:
    with open("refs.txt") as fp:
      Lines = fp.readlines()
      for l in Lines:
        m = regex.search(l)
        if m:
          r = m.group(0)
          print(f"Relation {r}")
          cont=2
          cur = None
          while(cont > 0):
            try:
              cur_version = None
              cur_waycount = 0
              if not cur:
                cur = overpass.query(query_cur_meta(r), timeout=QUERY_TIMEOUT)
                cur_version = int(cur._json["elements"][0]["tags"]["version"])
                cur_waycount = int(cur._json["elements"][0]["tags"]["waycount"])
                print(f'  cur version {cur_version}')
                print(f'  #ways {cur_waycount}')

                if (pow(cur_version, 1.5) * cur_waycount > MAX_WAY_VERSION_PRODUCT):
                  logger.error(f"Skipping relation {r} because it's too big")
                  cont = 0
                  continue

              rhist = overpass.query(query_hist_meta(r), timeout=QUERY_TIMEOUT)
            except Exception as e:
              # We won't get anything else than generic Exception instances here :(
              # See https://github.com/mocnik-science/osm-python-tools/issues/43
              if (e.args[0] and e.args[0].startswith('[overpass] error in result (cache')):
                logger.error(f"Download {r} timed out.")
                cont -= 1
                continue # retry

              if (hasattr(e, "args") and e.args[0].startswith("The requested data could not be downloaded. HTTP Error 429: Too Many Requests")):
                logger.error("Got 429: Too Many Requests, waiting a bit and retrying")
                time.sleep(TOO_MANY_REQUESTS_WAIT)
                cont=1
                continue

              if (hasattr(e, "args") and e.args[0].startswith("[overpass] could not fetch or interpret status of the endpoint")):
                logger.error("Are you online? Something is really broken...")
                raise e

              if (not hasattr(e, "args") or e.args[0].startswith("The requested data could not be downloaded.  ")):
                raise e

              logger.error(f'Could not fetch metadata for relation {r} (HTTPError), continuing with next relation.')
              cont=0
              continue
            break
          else:
            # We get here on HTTP errors (i.e., timeouts) and persisting cache problems, try next relation
            continue

          lowest = sys.maxsize
          creator = None

          for v in rhist.elements():
            if (not v._json or not v._json["tags"] or not v._json["tags"]["version"]):
              logger.error(f"There is something wrong with one of the versions of relation {r}, ignoring")
              continue
            user = v._json["tags"]["user"]
            version = int(v._json["tags"]["version"])
            
            if version < lowest:
              lowest = version
              creator = user

            if user in users:
              users[user] = users[user] + 1
            else:
              users[user] = 1

          if not creator:
            print("Relation %d does not have a creator? Wat?" % r)
          else:
            if creator in creators:
              creators[creator] = creators[creator] + 1
            else:
              creators[creator] = 1
  except Exception as e:
    logger.error(e)
    sys.exit(0)

  def print_numdict_reverse(d, topn=None, minval=1):
    for i,k in enumerate(sorted(d, key=d.get, reverse=True)):
      if (not topn or i < topn) and (d[k] >= minval):
        print("%s: %d" % (k, d[k]))

  topn = 20
  #  minval = 3

  #  print("Users:")
  #  print_numdict_reverse(users)

  #  print()

  print("Users (top %d out of %d):" % (topn, len(users)))
  print_numdict_reverse(users, topn)

  #  print()

  #  print("Users (min edits: %d):" % minval)
  #  print_numdict_reverse(users, minval = minval)

  print()

  topn = 20
  minval = 2

  #  print("Creators:")
  #  print_numdict_reverse(creators)

  #  print()

  print("Creators (top %d out of %d):" % (topn, len(creators)))
  print_numdict_reverse(creators, topn)

  print()

  print("Creators (min creates: %d):" % minval)
  print_numdict_reverse(creators, minval = minval)

if __name__ == '__main__':
    main()
