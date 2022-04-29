from flask import Flask
from flask import render_template
from flask import url_for
from flask import Response
from flask import g
from flask import request
import sqlite3
import re
import urllib.parse
from datetime import datetime

app = Flask(__name__)

DATABASE = 'blog.db'

def get_db():
  db = getattr(g, '_database', None)
  if db is None:
    db = g._database = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
  return db

@app.teardown_appcontext
def close_connection(exception):
  db = getattr(g, '_database', None)
  if db is not None:
    db.close()

def query_db(query, args=(), one=False):
  cur = get_db().execute(query, args)
  rv = cur.fetchall()
  cur.close()
  return (rv[0] if rv else None) if one else rv

@app.route('/', methods=['GET'])
def index():
  posts = []
  PAGESIZE = 30     # 每页显示的博文数量

  published_max = request.args.get('published-max', '')
  print(published_max)
  if published_max != '':
    rows = query_db('SELECT *, (SELECT count(*) FROM comments WHERE post_id=posts.id) as comment_total FROM posts WHERE published<=? ORDER BY published DESC LIMIT ?', (published_max, PAGESIZE))
  else:
    rows = query_db('SELECT *, (SELECT count(*) FROM comments WHERE post_id=posts.id) as comment_total FROM posts ORDER BY published DESC LIMIT ?', (PAGESIZE,))

  for row in rows:
    post = {}
    post['published'] = datetime.strptime(row['published'], '%Y-%m-%dT%H:%M:%S.%f%z')
    post['title'] = row['title']
    post['content'] = re.sub('<.*?>', '', row['content'])[0:150] + '...'
    post['link'] = '/' + row['published'][0:4] + '/' + row['published'][5:7] + '/' + row['file_name']
    post['comment_total'] = row['comment_total']
    posts.append(post)

  first_row_published = rows[0]['published']
  last_row_published = rows[-1]['published']

  # 获取下一页第一条的发布时间
  row = query_db('SELECT published FROM posts WHERE published<? ORDER BY published DESC', (last_row_published,), one=True)
  next_page_published = urllib.parse.quote(row['published']) if row else None

  # 获取上一页第一条的发布时间
  rows = query_db('SELECT published FROM posts WHERE published>? LIMIT ?', (first_row_published, PAGESIZE))
  prev_page_published = urllib.parse.quote(rows[-1]['published']) if len(rows) > 0 else None

  return render_template('index.html', posts=posts, next_page_published=next_page_published, prev_page_published=prev_page_published)

def load_local_image_map():
  img_map = {}

  rows = query_db('SELECT * FROM images')
  for row in rows:
    if row['local_file']:
      img_map[row['url']] = '/' + row['local_file']

  url_for('static', filename='anon36.png')
  url_for('static', filename='blogger_logo_round_35.png')
  rows = query_db('SELECT * FROM head_imgs')
  for row in rows:
    if row['local_file'] and row['url'] != 'https://img1.blogblog.com/img/blank.gif':
      if row['url'] == 'https://img1.blogblog.com/img/b16-rounded.gif':
        img_map[row['url']] = '/static/blogger_logo_round_35.png'
      else:
        img_map[row['url']] = '/' + row['local_file']
    else:
      img_map[row['url']] = '/static/anon36.png'
  return img_map

@app.route('/<year>/<month>/<name>')
def post(year, month, name):
  img_map = load_local_image_map()

  row = query_db('SELECT *, (SELECT count(*) FROM comments WHERE post_id=posts.id) as comment_total FROM posts WHERE substr(published,1,7)=? AND file_name=?', (f'{year}-{month}', name), one=True)
  post_content = {}
  post_content['published'] = datetime.strptime(row['published'], '%Y-%m-%dT%H:%M:%S.%f%z')
  post_content['title'] = row['title']
  post_content['content'] = re.sub('href="https?\://program\-think\.blogspot\.com/(.*?)"', 'href="/\\1"', row['content'])  # 将博文中指向其它博文的超链接替换为本地链接
  post_content['comment_total'] = row['comment_total']

  imgs = re.findall('<img[^>]*?src=\"(.*?)\".*?>', post_content['content'])
  for img in imgs:
    local_file = img_map[img]
    if local_file:
      post_content['content'] = post_content['content'].replace(img, local_file)    # 将网络图片地址替换成本地本址

  # 加载上一篇博文地址
  next_post = query_db('SELECT substr(published,1,4) as year, substr(published,6,2) as month, file_name FROM posts WHERE published>? ORDER BY published LIMIT 1', (row['published'],), one=True)

  # 加载下一篇博文地址
  prev_post = query_db('SELECT substr(published,1,4) as year, substr(published,6,2) as month, file_name FROM posts WHERE published<? ORDER BY published DESC LIMIT 1', (row['published'],), one=True)

  # 加载博文评论
  rows = query_db('SELECT * FROM comments WHERE post_id=?', (row['id'],))

  comments = []
  comment_root = {}
  for row in rows:
    comment = {}
    comment['id'] = row['id']
    comment['published'] = datetime.strptime(row['published'], '%Y-%m-%dT%H:%M:%S.%f%z')
    comment['content'] = re.sub('href="https?\://program\-think\.blogspot\.com/(.*?)"', 'href="/\\1"', row['content'])  # 将评价中指向其它博文的超链接替换为本地链接
    comment['author'] = row['author']
    comment['author_img'] = img_map[row['author_img']]
    comment['is_blogger'] = row['author_uri'] and ('11741356469378252621' in row['author_uri'])   # 标记本条评论是否是博主本人发的

    # 处理评论的二级分类
    if row['related_id'] == None:
      comment['replies'] = []
      comment_root[row['id']] = comment
      comments.append(comment)
    else:
      parent = comment_root[row['related_id']]
      parent['replies'].append(comment)

  return render_template('post.html', post=post_content, comments=comments, next_post=next_post, prev_post=prev_post)

# 本地博文图片接口
@app.route("/images/<date>/<name>")
def image(date, name):
  with open(f'images/{date}/{name}', 'rb') as img_f:
    img_stream = img_f.read()
    resp = Response(img_stream, mimetype="image")
    return resp

# 本地用户头像接口
@app.route("/head_imgs/<id>/<name>")
def head_img(id, name):
  with open(f'head_imgs/{id}/{name}', 'rb') as img_f:
    img_stream = img_f.read()
    resp = Response(img_stream, mimetype="image")
    return resp
