import sqlite3
import os
import urllib.request
import urllib.parse
import urllib.error
import json
import re
import time
import http
from signal import signal, SIGINT
from sys import exit

conn = None
cur = None

# 调用blogspot的api接口获取博文数据
# https://developers.google.com/blogger/docs/2.0/developers_guide_protocol
def get_posts(start_index, max_results=50, published_min=None):
  url = 'https://program-think.blogspot.com/feeds/posts/full'
  data = {}
  data['alt'] = 'json'
  data['start-index'] = start_index
  data['max-results'] = max_results
  if published_min != None:
    data['published-min'] = published_min
  data['orderby'] = 'published'
  data['reverse'] = 'true'
  full_url = url + '?' + urllib.parse.urlencode(data)
  try:
    with urllib.request.urlopen(full_url) as response:
      result = response.read().decode('utf-8')
      return json.loads(result)['feed']
  except (urllib.error.URLError, urllib.error.HTTPError, http.client.IncompleteRead, ConnectionError) as e:
    print(e)
  return False

# 调用blogspot的api接口获取评论数据
def get_comments(start_index, max_results=500, published_min=None):
  url = 'https://program-think.blogspot.com/feeds/comments/full'
  data = {}
  data['alt'] = 'json'
  data['v'] = 2
  data['start-index'] = start_index
  data['max-results'] = max_results
  if published_min != None:
    data['published-min'] = published_min
  data['orderby'] = 'published'
  data['reverse'] = 'false'
  full_url = url + '?' + urllib.parse.urlencode(data)
  try:
    with urllib.request.urlopen(full_url) as response:
      result = response.read().decode('utf-8')
      return json.loads(result)['feed']
  except (urllib.error.URLError, urllib.error.HTTPError, http.client.IncompleteRead, ConnectionError) as e:
    print(e)
  return False

# 将博文标签转成“|”隔开的字符串格式
def get_category_str(categorys):
  str = ''
  for category in categorys:
    if str != '':
      str = str + '|' + category['term']
    else:
      str = str + category['term']
  return str

# 获取本地数据库中最后一篇博文的发布时间
def local_last_post_published():
  cur.execute('SELECT published FROM posts ORDER BY published DESC')
  row = cur.fetchone()
  if row != None:
    return row[0]

# 获取本地数据库中最后一条评论的发布时间
def local_last_comment_published():
  cur.execute('SELECT published FROM comments ORDER BY published DESC')
  row = cur.fetchone()
  if row != None:
    return row[0]

# 添加博文到本地数据库中
def update_post(id, published, updated, category, title, content, file_name):
  cur.execute('SELECT * FROM posts WHERE id=?', (id,))
  row = cur.fetchone()
  if row != None:
    cur.execute('UPDATE posts set published=?,updated=?,category=?,title=?,content=?,file_name=? WHERE id=?', (published, updated, category, title, content, file_name, id))
  else:
    post = (id, published, updated, category, title, content, file_name)
    cur.execute('INSERT INTO posts VALUES(?, ?, ?, ?, ?, ?, ?)', post)

# 添加评论到本地数据库中
def update_comment(id, published, updated, content, author, author_uri, author_img, post_id, related_id):
  cur.execute('SELECT * FROM comments WHERE id=?', (id,))
  row = cur.fetchone()
  if row != None:
    cur.execute('UPDATE comments set published=?,updated=?,content=?,author=?,author_uri=?,author_img=?,post_id=?,related_id=? WHERE id=?', (published, updated, content, author, author_uri, author_img, post_id, related_id, id))
  else:
    comment = (id, published, updated, content, author, author_uri, author_img, post_id, related_id)
    cur.execute('INSERT INTO comments VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)', comment)

# 解析出博文中所有图片地址并保存到images表中
def hold_images(post_content, post_id):
  imgs = re.findall('<img[^>]*?src=\"(.*?)\".*?>', post_content)
  for img in imgs:
    cur.execute('SELECT * FROM images WHERE url=?', (img,))
    row = cur.fetchone()
    if row == None:
      cur.execute('INSERT INTO images(url, post_id) VALUES(?, ?)', (img, post_id))

# 保存用户头像地址
def hold_head_img(img_url):
  cur.execute('SELECT * FROM head_imgs WHERE url=?', (img_url,))
  row = cur.fetchone()
  if row == None:
    cur.execute('INSERT INTO head_imgs(url) VALUES(?)', (img_url,))

# 同步博文到本地数据库
def sync_posts():
  count = 0
  post_published_min = local_last_post_published()
  print(f'开始同步博文，本地博文最后更新时间：{post_published_min}')

  while True:
    start_index = count + 1
    posts = get_posts(start_index, published_min=post_published_min)
    if not posts:
      print('下载数据失败，5秒后重试')
      time.sleep(5)
      continue

    for post in posts['entry']:
      id = re.match('.*?post-(\d+)', post['id']['$t']).group(1)
      published = post['published']['$t']
      updated = post['updated']['$t']
      category = get_category_str(post['category'])
      title = post['title']['$t']
      content = post['content']['$t']

      file_name = None
      for i in range(0, len(post['link'])):
        if post['link'][i]['rel'] == 'alternate':
          file_name = re.match('.*/([^/]+)$', post['link'][i]['href']).group(1)

      count = count + 1
      print(count, f'id={id},category={category},title={title},file_name={file_name}')
      update_post(id, published, updated, category, title, content, file_name)
      hold_images(content, id)

    conn.commit()
    if count >= int(posts['openSearch$totalResults']['$t']):
      print(f'同步完成，本次共计更新博文 {count} 篇')
      break

# 同步评论到本地数据库
def sync_comments():
  count = 0
  comment_published_min = local_last_comment_published()
  print(f'开始同步评论，本地评论最后更新时间：{comment_published_min}')

  # start-index传1时无法从openSearch$totalResults获取真实的评论总数，这里只能多做一步用于获取评论数
  comments = get_comments(1000, 1, comment_published_min)
  total_comments = int(comments['openSearch$totalResults']['$t'])
  print(f'待导入评论数：{total_comments}')

  while True:
    start_index = count + 1
    comments = get_comments(start_index, published_min=comment_published_min)
    if not comments:
      print('下载数据失败，5秒后重试')
      time.sleep(5)
      continue

    for comment in comments['entry']:
      id = re.match('.*?post-(\d+)', comment['id']['$t']).group(1)
      published = comment['published']['$t']
      updated = comment['updated']['$t']
      content = comment['content']['$t']
      author = comment['author'][0]['name']['$t']
      author_img = comment['author'][0]['gd$image']['src']

      if 'uri' in comment['author'][0]:
        author_uri = comment['author'][0]['uri']['$t']
      else:
        author_uri = None

      if len(comment['link']) >= 4:
        releated = comment['link'][3]['href']
        parent_id = re.match('.*?feeds/(\d+)/(\d+)/comments/default/(\d+).*', releated)
        post_id = parent_id.group(2)
        related_id = parent_id.group(3)
      else:
        releated = comment['link'][0]['href']
        parent_id = re.match('.*?feeds/(\d+)/(\d+)/comments/default/(\d+).*', releated)
        post_id = parent_id.group(2)
        related_id = None

      count = count + 1
      #print(count, f'id={id},author={author},content={content}')
      update_comment(id, published, updated, content, author, author_uri, author_img, post_id, related_id)
      hold_head_img(author_img)

    conn.commit()   # 往数据库中写入本轮数据
    print(f'已导入 {count} 条评论')
    if count >= total_comments:
      print(f'同步完成，本次共计更新评论 {count} 条')
      break

def download_file(url, save_path, prefix=''):
  os.makedirs(save_path, exist_ok=True)
  try:
    headers={}
    headers['User-Agent'] = "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2228.0 Safari/537.36"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as response:
      content_desc = response.getheader('Content-Disposition')
      if content_desc != None:
        file_name = urllib.parse.unquote(re.match('.*filename="(.*?)".*', content_desc).group(1))
        file_name = re.sub('[\*\?\:]', '_', file_name)
      else:
        file_name = re.match('.*/([^/]+?)(?:\?.*)?$', url).group(1)
      path = f'{save_path}/{prefix}{file_name}'
      with open(path, 'wb') as file:
        file.write(response.read())
        return path
  except (urllib.error.URLError, urllib.error.HTTPError, http.client.IncompleteRead, ConnectionError) as e:
    print(e)
  return False

# 下载博文配图
def download_post_images():
  os.makedirs('./images/', exist_ok=True)
  cur.execute('SELECT images.id, images.url, posts.published, images.local_file FROM images INNER JOIN posts ON images.post_id=posts.id')
  rows = cur.fetchall()

  print('开始下载博文配图')
  success = True
  count = 0
  for row in rows:
    id = row[0]
    url = row[1]
    if url[0:5] == 'http:':
      url = 'https:' + url[5:]    # 部分旧博文配图使用的是http链接，需要转成https才能访问
    dir_name = row[2][0:10]  # 截取博文发布日期作为博文配图的存放目录
    local_file = row[3]
    if local_file != None and os.path.exists(local_file):
      continue

    local_file = download_file(url, f'./images/{dir_name}', prefix=f'{id}-')
    if not local_file:
      print(f'图片下载失败，url={url}')
      success = False
    else:
      cur.execute('UPDATE images SET local_file=? WHERE id=?', (local_file, id))
      conn.commit()
      count = count + 1
      if count % 10 == 0:
        print(f'已下载 {count} 张图片', end='\r', flush=True)

  if not success:
    print('部分图片下载失败，请稍后重试')
  else:
    print(f'下载完成，本次共计下载图片 {count} 张')

# 下载评论区用户头像
def download_head_imgs():
  os.makedirs('./head_imgs/', exist_ok=True)
  cur.execute('SELECT id, url, local_file FROM head_imgs')
  rows = cur.fetchall()

  print('开始下载用户头像')
  success = True
  count = 0
  for row in rows:
    id = row[0]
    url = row[1]
    if url[0:2] == '//':
      url = 'https:' + url
    url = url[0:7] + urllib.parse.quote(url[7:])
    local_file = row[2]
    if local_file != None and os.path.exists(local_file):
      continue

    local_file = download_file(url, f'./head_imgs/{id}')
    if not local_file:
      print(f'图片下载失败，url={url}')
      success = False
    else:
      cur.execute('UPDATE head_imgs SET local_file=? WHERE id=?', (local_file, id))
      conn.commit()
      count = count + 1
      if count % 10 == 0:
        print(f'已下载 {count} 张图片', end='\r', flush=True)

  if not success:
    print('部分图片下载失败，请稍后重试')
  else:
    print(f'下载完成，本次共计下载图片 {count} 张')

def handler(signal_received, frame):
  print('中断任务')
  if conn != None:
    conn.close()
  exit(0)

def main():
  signal(SIGINT, handler)

  global conn, cur
  conn = sqlite3.connect('blog.db')
  cur = conn.cursor()

  sql = '''CREATE TABLE IF NOT EXISTS posts (
             id INT PRIMARY KEY NOT NULL,
             published TEXT,
             updated TEXT,
             category TEXT,
             title TEXT,
             content TEXT,
             file_name TEXT
           );'''
  cur.execute(sql)

  sql = '''CREATE TABLE IF NOT EXISTS comments (
             id INT PRIMARY KEY NOT NULL,
             published TEXT,
             updated TEXT,
             content TEXT,
             author TEXT,
             author_uri TEXT,
             author_img TEXT,
             post_id INT NOT NULL,
             related_id INT
           );'''
  # post_id 指向评论对应的博文
  # related_id 指出当前评论是否是对其它评论的回复
  cur.execute(sql)

  sql = '''CREATE INDEX IF NOT EXISTS post_comments_index ON comments (
             post_id
           );'''
  cur.execute(sql)

  sql = '''CREATE TABLE IF NOT EXISTS images (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             url TEXT UNIQUE NOT NULL,
             post_id INT NOT NULL,
             local_file TEXT
           );'''
  cur.execute(sql)

  sql = '''CREATE TABLE IF NOT EXISTS head_imgs (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             url TEXT UNIQUE NOT NULL,
             local_file TEXT
           );'''
  cur.execute(sql)
  conn.commit()

  try:
    sync_posts()            # 同步博文
    sync_comments()         # 同步评论
    download_post_images()  # 下载博文配图
    download_head_imgs()    # 下载用户头像
  except Exception as e:
    print(e)
  finally:
    conn.close()

main()

