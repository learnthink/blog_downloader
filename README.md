# 编程随想博客下载器

这套脚本用于下载编程随想博客上的博文、博文配图、评论、用户头像

## 首先，克隆这个仓库
```
git clone https://github.com/learnthink/blog_downloader.git
```

## 下载博客数据
运行同步脚本，程序将自动下载博文和评论并储存到 'blog.db' 文件中，之后程序会继续下载图片和用户头像，并分别保存至 'images' 和 'head_imgs' 目录中，下载图片如果遇到网络错误，一般多试几次就好了。或者也可以直接下载我已经下好的数据： https://github.com/learnthink/blog_downloader/releases/tag/v0.1 ，然后解压到脚本根目录下
```
python3 ./sync_data.py
```

## 浏览已下载的数据
本套脚本附带一个小型WEB服务程序，用于浏览下载好的数据，启动后在浏览器中输入 http://127.0.0.1:5000 进行访问

### 开启方式
Windows：
```
run_server.bat
```

Linux:
```
./run_server.sh
```
