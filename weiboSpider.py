    #!/usr/bin/env python
# -*- coding: UTF-8 -*-

import codecs
import csv
import json
import os
import random
import re
import sys
import traceback
from collections import OrderedDict
from datetime import datetime, timedelta
from time import sleep

import requests
from lxml import etree
from requests.adapters import HTTPAdapter
from tqdm import tqdm

class Weibo(object):
    config = {}

    def __load_config(self, config, key, default_value, presets=None, errmsg=None):
        if not key in config:
            self.config[key] = default_value
        elif presets == None or config[key] in presets:
            self.config[key] = config[key]
        elif errmsg != None:
            sys.exit(errmsg)
        else:
            self.config[key] = default_value

    def __init__(self, user_id, config={}):
        """Weibo类初始化"""
        if not isinstance(user_id, int):
            sys.exit(u'user_id值应为一串数字形式,请重新输入')
        if not isinstance(config, dict):
            sys.exit(u'config值应为字典形式,请重新输入')
        self.__load_config(config, 'only_original', 0, [0, 1], u'only_original值应为0或1,0代表要爬取用户的全部微博,1代表只爬取用户的原创微博,请重新输入')
        self.__load_config(config, 'pic_download', 0, [0, 1], u'pic_download值应为0或1,0代表不下载微博原始图片,1代表下载,请重新输入')
        self.__load_config(config, 'video_download', 0, [0, 1], u'video_download值应为0或1,0代表不下载微博视频,1代表下载,请重新输入')
        self.__load_config(config, 'order', 0, ['time asc', 'time desc'], u'order值应为time asc或time desc,time asc代表时间升序,time desc代表时间降序,请重新输入')
        self.__load_config(config, 'cookie', '')
        self.__load_config(config, 'debug', False, [True, False], u'debug值应为0或1,0代表关闭测试输出,1代表开启,请重新输入')
        self.user_id = user_id  # 用户id,即需要我们输入的数字,如昵称为"Dear-迪丽热巴"的id为1669879400
        self.nickname = ''  # 用户昵称,如“Dear-迪丽热巴”
        self.weibo_num = 0  # 用户全部微博数
        self.got_num = 0  # 爬取到的微博数
        self.following = 0  # 用户关注数
        self.followers = 0  # 用户粉丝数
        self.weibo = []  # 存储爬取到的所有微博信息

    def write_log(self, *args):
        if self.config['debug']:
            print(*args)

    def request(self, url):
        wait_time = 0
        while True:
            # 通过加入步进等待避免被限制。微博页面访问有速度限制，单位时间超过允许
            # 最大次数会被系统限制(一段时间后限制会自动解除)，加入步进等待可处理改
            # 系统限制。默认是每触发一次限制步进10秒，可根据情况增减步进时间
            response = requests.get(url, cookies={'Cookie': self.config['cookie']})
            if response.status_code == 418:
                wait_time += 10
                print(u'错误418：访问超限，等待%d秒后重试 %s' % (wait_time, url))
                sleep(wait_time)
            else:
                break
        return response

    def deal_html(self, url):
        """处理html"""
        try:
            response = self.request(url)
            selector = etree.HTML(response.content)
            return selector
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def deal_garbled(self, info):
        """处理乱码"""
        try:
            info = (info.xpath('string(.)').replace(u'\u200b', '').encode(
                sys.stdout.encoding, 'ignore').decode(sys.stdout.encoding))
            return info
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_nickname(self):
        """获取用户昵称"""
        try:
            url = 'https://weibo.cn/%d/info' % (self.user_id)
            selector = self.deal_html(url)
            nickname = selector.xpath('//title/text()')[0]
            self.nickname = nickname[:-3]
            if self.nickname == u'登录 - 新' or self.nickname == u'新浪':
                sys.exit(u'cookie错误或已过期,请按照README中方法重新获取')
            print(u'用户昵称: ' + self.nickname)
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_user_info(self, selector):
        """获取用户昵称、微博数、关注数、粉丝数"""
        try:
            self.get_nickname()  # 获取用户昵称
            user_info = selector.xpath("//div[@class='tip2']/*/text()")

            self.weibo_num = int(user_info[0][3:-1])
            print(u'微博数: ' + str(self.weibo_num))

            self.following = int(user_info[1][3:-1])
            print(u'关注数: ' + str(self.following))

            self.followers = int(user_info[2][3:-1])
            print(u'粉丝数: ' + str(self.followers))
            print('*' * 100)
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_page_num(self, selector):
        """获取微博总页数"""
        try:
            if selector.xpath("//input[@name='mp']") == []:
                page_num = 1
            else:
                page_num = (int)(
                    selector.xpath("//input[@name='mp']")[0].attrib['value'])
            return page_num
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_long_weibo(self, weibo_link):
        """获取长原创微博"""
        try:
            selector = self.deal_html(weibo_link)
            info = selector.xpath("//div[@class='c']")[1]
            wb_content = self.deal_garbled(info)
            wb_time = info.xpath("//span[@class='ct']/text()")[0]
            weibo_content = wb_content[wb_content.find(':') +
                                       1:wb_content.rfind(wb_time)]
            return weibo_content
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()
        return u'网络出错'

    def get_original_weibo(self, info, weibo_id):
        """获取原创微博"""
        try:
            weibo_content = self.deal_garbled(info)
            weibo_content = weibo_content[:weibo_content.rfind(u'赞')]
            a_text = info.xpath('div//a/text()')
            if u'全文' in a_text:
                weibo_link = 'https://weibo.cn/comment/' + weibo_id + '?ckAll=1'
                wb_content = self.get_long_weibo(weibo_link)
                if wb_content:
                    weibo_content = wb_content
            return {'overview': weibo_content, 'origin': weibo_content,
                    'original_user': u'原创', 'retweet_reason': ''}
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_long_retweet(self, weibo_link):
        """获取长转发微博"""
        try:
            wb_content = self.get_long_weibo(weibo_link)
            weibo_content = wb_content[:wb_content.rfind(u'原文转发')]
            return weibo_content
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_retweet(self, info, weibo_id):
        """获取转发微博"""
        try:
            original_user = info.xpath("div/span[@class='cmt']/a/text()")
            if original_user:
                original_user = original_user[0]
                wb_content = self.deal_garbled(info)
                wb_content = wb_content[wb_content.find(':') +
                                        1:wb_content.rfind(u'赞')]
                wb_content = wb_content[:wb_content.rfind(u'赞')]
                a_text = info.xpath('div//a/text()')
                if u'全文' in a_text:
                    weibo_link = 'https://weibo.cn/comment/' + weibo_id
                    weibo_content = self.get_long_retweet(weibo_link)
                    if weibo_content:
                        wb_content = weibo_content
            else:
                original_user = u'已删除'
                wb_content = u'转发微博已被删除'
            retweet_reason = self.deal_garbled(info.xpath('div')[-1])
            retweet_reason = retweet_reason[retweet_reason.find(':') +
                                        1:retweet_reason.rindex(u'赞')]
            wb_overview = (retweet_reason + '\n' + u'原始用户: ' + original_user +
                          '\n' + u'转发内容: ' + wb_content)
            return {'overview': wb_overview, 'origin': wb_content,
                    'original_user': original_user, 'retweet_reason': retweet_reason}
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def is_original(self, info):
        """判断微博是否为原创微博"""
        is_original = info.xpath("div/span[@class='cmt']")
        if len(is_original) > 3:
            return False
        else:
            return True

    def get_weibo_content(self, info, is_original):
        """获取微博内容"""
        try:
            weibo_id = info.xpath('@id')[0][2:]
            if is_original:
                weibo_content = self.get_original_weibo(info, weibo_id)
            else:
                weibo_content = self.get_retweet(info, weibo_id)
            self.write_log(weibo_content)
            return weibo_content
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_publish_place(self, info):
        """获取微博发布位置"""
        try:
            div_first = info.xpath('div')[0]
            a_list = div_first.xpath('a')
            publish_place = u'无'
            for a in a_list:
                if ('place.weibo.com' in a.xpath('@href')[0]
                        and a.xpath('text()')[0] == u'显示地图'):
                    weibo_a = div_first.xpath("span[@class='ctt']/a")
                    if len(weibo_a) >= 1:
                        publish_place = weibo_a[-1]
                        if (u'视频' == div_first.xpath(
                                "span[@class='ctt']/a/text()")[-1][-2:]):
                            if len(weibo_a) >= 2:
                                publish_place = weibo_a[-2]
                            else:
                                publish_place = u'无'
                        publish_place = self.deal_garbled(publish_place)
                        break
            self.write_log(u'微博发布位置: ' + publish_place)
            return publish_place
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_publish_time(self, info):
        """获取微博发布时间"""
        try:
            str_time = info.xpath("div/span[@class='ct']")
            str_time = self.deal_garbled(str_time[0])
            publish_time = str_time.split(u'来自')[0]
            if u'刚刚' in publish_time:
                publish_time = datetime.now().strftime('%Y-%m-%d %H:%M')
            elif u'分钟' in publish_time:
                minute = publish_time[:publish_time.find(u'分钟')]
                minute = timedelta(minutes=int(minute))
                publish_time = (datetime.now() -
                                minute).strftime('%Y-%m-%d %H:%M')
            elif u'今天' in publish_time:
                today = datetime.now().strftime('%Y-%m-%d')
                time = publish_time[3:]
                publish_time = today + ' ' + time
            elif u'月' in publish_time:
                year = datetime.now().strftime('%Y')
                month = publish_time[0:2]
                day = publish_time[3:5]
                time = publish_time[7:12]
                publish_time = year + '-' + month + '-' + day + ' ' + time
            else:
                publish_time = publish_time[:16]
            self.write_log(u'微博发布时间: ' + publish_time)
            return publish_time
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_publish_tool(self, info):
        """获取微博发布工具"""
        try:
            str_time = info.xpath("div/span[@class='ct']")
            str_time = self.deal_garbled(str_time[0])
            if len(str_time.split(u'来自')) > 1:
                publish_tool = str_time.split(u'来自')[1]
            else:
                publish_tool = u'无'
            self.write_log(u'微博发布工具: ' + publish_tool)
            return publish_tool
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_weibo_footer(self, info):
        """获取微博点赞数、转发数、评论数"""
        try:
            footer = {}
            pattern = r'\d+'
            str_footer = info.xpath('div')[-1]
            str_footer = self.deal_garbled(str_footer)
            str_footer = str_footer[str_footer.rfind(u'赞'):]
            weibo_footer = re.findall(pattern, str_footer, re.M)

            up_num = int(weibo_footer[0])
            self.write_log(u'点赞数: ' + str(up_num))
            footer['up_num'] = up_num

            retweet_num = int(weibo_footer[1])
            self.write_log(u'转发数: ' + str(retweet_num))
            footer['retweet_num'] = retweet_num

            comment_num = int(weibo_footer[2])
            self.write_log(u'评论数: ' + str(comment_num))
            footer['comment_num'] = comment_num
            return footer
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def extract_picture_urls(self, info, weibo_id):
        """提取微博原始图片url"""
        try:
            a_list = info.xpath('div/a/@href')
            first_pic = 'https://weibo.cn/mblog/pic/' + weibo_id + '?rl=0'
            all_pic = 'https://weibo.cn/mblog/picAll/' + weibo_id + '?rl=1'
            if first_pic in a_list:
                if all_pic in a_list:
                    selector = self.deal_html(all_pic)
                    preview_picture_list = selector.xpath('//img/@src')
                    picture_list = [
                        p.replace('/thumb180/', '/large/')
                        for p in preview_picture_list
                    ]
                    picture_urls = ','.join(picture_list)
                else:
                    if info.xpath('.//img/@src'):
                        preview_picture = info.xpath('.//img/@src')[-1]
                        picture_urls = preview_picture.replace(
                            '/wap180/', '/large/')
                    else:
                        sys.exit(
                            u"爬虫微博可能被设置成了'不显示图片'，请前往"
                            u"'https://weibo.cn/account/customize/pic'，修改为'显示'"
                        )
            else:
                picture_urls = u'无'
            return picture_urls
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()
        return u'无'

    def get_picture_urls(self, info, is_original):
        """获取微博原始图片url"""
        try:
            weibo_id = info.xpath('@id')[0][2:]
            picture_urls = {'original_pictures': u'无', 'retweet_pictures': u'无'}
            if is_original:
                original_pictures = self.extract_picture_urls(info, weibo_id)
                picture_urls['original_pictures'] = original_pictures
            else:
                retweet_url = info.xpath("div/a[@class='cc']/@href")[0]
                retweet_id = retweet_url.split('/')[-1].split('?')[0]
                retweet_pictures = self.extract_picture_urls(info, retweet_id)
                picture_urls['retweet_pictures'] = retweet_pictures
                a_list = info.xpath('div[last()]/a/@href')
                original_pictures = u'无'
                for a in a_list:
                    if a.endswith(('.gif', '.jpeg', '.jpg', '.png')):
                        original_pictures = a
                        break
                picture_urls['original_pictures'] = original_pictures
            return picture_urls
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_video_url(self, info, is_original):
        """获取微博视频url"""
        try:
            video_url = u'无'
            if is_original:
                div_first = info.xpath('div')[0]
                a_list = div_first.xpath('.//a')
                video_link = u'无'
                for a in a_list:
                    if 'm.weibo.cn/s/video/show?object_id=' in a.xpath(
                            '@href')[0]:
                        video_link = a.xpath('@href')[0]
                        break
                if video_link != u'无':
                    video_link = video_link.replace(
                        'm.weibo.cn/s/video/show', 'm.weibo.cn/s/video/object')
                    wb_info = self.request(video_link).json()
                    v_url = wb_info['data']['object']['stream'].get(
                        'hd_url')
                    if not v_url:
                        v_url = wb_info['data']['object']['stream']['url']
                    if v_url:  # 说明该视频不是直播
                        video_url = v_url
            return video_url
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()
        return u'无'

    def download_one_file(self, url, file_path, type, weibo_id):
        """下载单个文件(图片/视频)"""
        try:
            s = requests.Session()
            s.mount(url, HTTPAdapter(max_retries=5))
            downloaded = s.get(url, timeout=(5, 10))
            with open(file_path, 'wb') as f:
                f.write(downloaded.content)
        except Exception as e:
            error_file = self.get_filepath(
                type) + os.sep + 'not_downloaded.txt'
            with open(error_file, 'ab') as f:
                url = weibo_id + ':' + url + '\n'
                f.write(url.encode(sys.stdout.encoding))
            print('Error: ', e)
            traceback.print_exc()

    def download_files(self, type):
        """下载文件(图片/视频)"""
        try:
            if type == 'img':
                describe = u'图片'
                key = 'original_pictures'
            else:
                describe = u'视频'
                key = 'video_url'
            print(u'即将进行%s下载' % describe)
            file_dir = self.get_filepath(type)
            for w in tqdm(self.weibo, desc=u'%s下载进度' % describe):
                if w[key] != u'无':
                    file_prefix = w['publish_time'][:11].replace(
                        '-', '') + '_' + w['id']
                    if type == 'img' and ',' in w[key]:
                        w[key] = w[key].split(',')
                        for j, url in enumerate(w[key]):
                            file_suffix = url[url.rfind('.'):]
                            file_name = file_prefix + '_' + str(
                                j + 1) + file_suffix
                            file_path = file_dir + os.sep + file_name
                            self.download_one_file(url, file_path, type,
                                                   w['id'])
                    else:
                        if type == 'video':
                            file_suffix = '.mp4'
                        else:
                            file_suffix = w[key][w[key].rfind('.'):]
                        file_name = file_prefix + file_suffix
                        file_path = file_dir + os.sep + file_name
                        self.download_one_file(w[key], file_path, type,
                                               w['id'])
            print(u'%s下载完毕,保存路径:' % describe)
            print(file_dir)
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_one_weibo(self, info):
        """获取一条微博的全部信息"""
        try:
            weibo = OrderedDict()
            is_original = self.is_original(info)
            if (not self.config['only_original']) or is_original:
                weibo['id'] = info.xpath('@id')[0][2:]
                weibo['url'] = 'https://weibo.com/' + str(self.user_id) + '/' + weibo['id']
                content = self.get_weibo_content(info, is_original)  # 微博内容
                weibo['overview'] = content['overview']  # 微博总览
                weibo['is_original'] = is_original  # 是否原创微博
                weibo['original_user'] = content['original_user']  # 原作者
                weibo['retweet_reason'] = content['retweet_reason']  # 转发内容
                weibo['content'] = content['origin']  # 微博内容
                picture_urls = self.get_picture_urls(info, is_original)
                weibo['original_pictures'] = picture_urls['original_pictures']  # 原创图片url
                weibo['retweet_pictures'] = picture_urls['retweet_pictures']  # 转发图片url
                weibo['video_url'] = self.get_video_url(info, is_original)  # 微博视频url
                weibo['publish_place'] = self.get_publish_place(info)  # 微博发布位置
                weibo['publish_time'] = self.get_publish_time(info)  # 微博发布时间
                weibo['publish_tool'] = self.get_publish_tool(info)  # 微博发布工具
                footer = self.get_weibo_footer(info)
                weibo['up_num'] = footer['up_num']  # 微博点赞数
                weibo['retweet_num'] = footer['retweet_num']  # 转发数
                weibo['comment_num'] = footer['comment_num']  # 评论数
            else:
                weibo = None
            return weibo
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_one_page(self, page):
        """获取第page页的全部微博"""
        try:
            url = 'https://weibo.cn/%d/profile?page=%d' % (self.user_id, page)
            selector = self.deal_html(url)
            info = selector.xpath("//div[@class='c']")
            is_exist = info[0].xpath("div/span[@class='ctt']")
            if is_exist:
                info_len = len(info) - 2
                for i in range(0, info_len):
                    if self.config['order'] == 'time desc':
                        weibo = self.get_one_weibo(info[i])
                    else:
                        weibo = self.get_one_weibo(info[info_len - i - 1])
                    if weibo:
                        self.weibo.append(weibo)
                        self.got_num += 1
                        self.write_log('-' * 100)
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def get_filepath(self, type):
        """获取结果文件路径"""
        try:
            file_dir = os.path.split(os.path.realpath(
                __file__))[0] + os.sep + 'weibo' + os.sep + self.nickname
            if type == 'img' or type == 'video':
                file_dir = file_dir + os.sep + type
            if not os.path.isdir(file_dir):
                os.makedirs(file_dir)
            if type == 'img' or type == 'video':
                return file_dir
            file_path = file_dir + os.sep + '%d' % self.user_id + '.' + type
            return file_path
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def write_csv(self, wrote_num):
        """将爬取的信息写入csv文件"""
        try:
            result_headers = []
            result_headers.append('微博地址')
            if not self.config['only_original']:
                result_headers.append('是否为原创微博')
                result_headers.append('转发内容')
                result_headers.append('原作者')
            result_headers.append('微博正文')
            result_headers.append('原始图片url')
            if not self.config['only_original']:
                result_headers.append('被转发微博原始图片地址')
            result_headers.append('微博视频地址')
            result_headers.append('发布位置')
            result_headers.append('发布时间')
            result_headers.append('发布工具')
            result_headers.append('点赞数')
            result_headers.append('转发数')
            result_headers.append('评论数')
            result_data = []
            for w in self.weibo[wrote_num:]:
                d = []
                d.append(w['url'])
                if not self.config['only_original']:
                    d.append(w['is_original'])
                    d.append(w['retweet_reason'])
                    d.append(w['original_user'])
                d.append(w['content'])
                d.append(w['original_pictures'])
                if not self.config['only_original']:
                    d.append(w['retweet_pictures'])
                d.append(w['video_url'])
                d.append(w['publish_place'])
                d.append(w['publish_time'])
                d.append(w['publish_tool'])
                d.append(w['up_num'])
                d.append(w['retweet_num'])
                d.append(w['comment_num'])
                result_data.append(d)
            if sys.version < '3':  # python2.x
                reload(sys)
                sys.setdefaultencoding('utf-8')
                with open(self.get_filepath('csv'), 'ab') as f:
                    f.write(codecs.BOM_UTF8)
                    writer = csv.writer(f)
                    if wrote_num == 0:
                        writer.writerows([result_headers])
                    writer.writerows(result_data)
            else:  # python3.x
                with open(self.get_filepath('csv'),
                          'a',
                          encoding='utf-8-sig',
                          newline='') as f:
                    writer = csv.writer(f)
                    if wrote_num == 0:
                        writer.writerows([result_headers])
                    writer.writerows(result_data)
            print(u'%d条微博写入csv文件完毕,保存路径:' % self.got_num)
            print(self.get_filepath('csv'))
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def write_txt(self, wrote_num):
        """将爬取的信息写入txt文件"""
        try:
            temp_result = []
            if wrote_num == 0:
                if self.config['only_original']:
                    result_header = u'\n\n原创微博内容: \n'
                else:
                    result_header = u'\n\n微博内容: \n'
                result_header = (u'用户信息\n用户昵称：' + self.nickname + u'\n用户id: ' +
                                 str(self.user_id) + u'\n微博数: ' +
                                 str(self.weibo_num) + u'\n关注数: ' +
                                 str(self.following) + u'\n粉丝数: ' +
                                 str(self.followers) + result_header)
                temp_result.append(result_header)
            for i, w in enumerate(self.weibo[wrote_num:]):
                temp_result.append(
                    str(wrote_num + i + 1) + ':' + w['overview'] + '\n' +
                    u'微博位置: ' + w['publish_place'] + '\n' + u'发布时间: ' +
                    w['publish_time'] + '\n' + u'点赞数: ' + str(w['up_num']) +
                    u'   转发数: ' + str(w['retweet_num']) + u'   评论数: ' +
                    str(w['comment_num']) + '\n' + u'发布工具: ' +
                    w['publish_tool'] + '\n\n')
            result = ''.join(temp_result)
            with open(self.get_filepath('txt'), 'ab') as f:
                f.write(result.encode(sys.stdout.encoding))
            print(u'%d条微博写入txt文件完毕,保存路径:' % self.got_num)
            print(self.get_filepath('txt'))
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def write_file(self, wrote_num):
        """写文件"""
        if self.got_num > wrote_num:
            self.write_csv(wrote_num)
            self.write_txt(wrote_num)

    def get_weibo_info(self):
        """获取微博信息"""
        try:
            url = 'https://weibo.cn/%d/profile' % (self.user_id)
            selector = self.deal_html(url)
            self.get_user_info(selector)  # 获取用户昵称、微博数、关注数、粉丝数
            page_num = self.get_page_num(selector)  # 获取微博总页数
            wrote_num = 0
            page1 = 0
            random_pages = random.randint(1, 5)
            for page in tqdm(range(1, page_num + 1), desc=u'进度'):
                if self.config['order'] == 'time desc':
                    self.get_one_page(page)
                else:
                    self.get_one_page(page_num - page)

                if page % 20 == 0:  # 每爬20页写入一次文件
                    self.write_file(wrote_num)
                    wrote_num = self.got_num

                if page - page1 == random_pages and page < page_num:
                    page1 = page
                    random_pages = random.randint(1, 5)

            self.write_file(wrote_num)  # 将剩余不足20页的微博写入文件
            if not self.config['only_original']:
                print(u'共爬取' + str(self.got_num) + u'条微博')
            else:
                print(u'共爬取' + str(self.got_num) + u'条原创微博')
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()

    def start(self):
        """运行爬虫"""
        try:
            self.get_weibo_info()
            print(u'信息抓取完毕')
            print('*' * 100)
            if self.config['pic_download'] == 1:
                self.download_files('img')
            if self.config['video_download'] == 1:
                self.download_files('video')
        except Exception as e:
            print('Error: ', e)
            traceback.print_exc()


def main():
    try:
        # 使用实例,输入一个用户id，所有信息都会存储在wb实例中
        try:
            with open(os.path.split(os.path.realpath(__file__))[0] + os.sep + 'config.json', 'r') as f:
                jconfig = json.load(f)
        except Exception as e:
            print(u'请正确配置 config.json 文件，可从模板文件 config.json.tpl 创建。')
            exit()
        user_id = int(jconfig.get('user_id'))  # 可以改成任意合法的用户id（爬虫的微博id除外）
        config = {
            'only_original': jconfig.get('only_original'),  # 值为0表示爬取全部微博（原创微博+转发微博），值为1表示只爬取原创微博
            'pic_download': jconfig.get('pic_download'),  # 值为0代表不下载微博原始图片,1代表下载微博原始图片
            'video_download': jconfig.get('video_download'),  # 值为0代表不下载微博视频,1代表下载微博视频
            'cookie': jconfig.get('cookie'),  # 抓取时的cookie信息
            'order': jconfig.get('order'),  # 抓取时的顺序，time asc表示时间轴升序，time desc表示时间轴降序
        }
        wb = Weibo(user_id, config)  # 调用Weibo类，创建微博实例wb
        wb.start()  # 爬取微博信息
        print(u'用户昵称: ' + wb.nickname)
        print(u'全部微博数: ' + str(wb.weibo_num))
        print(u'关注数: ' + str(wb.following))
        print(u'粉丝数: ' + str(wb.followers))
        if wb.weibo:
            print(u'最新/置顶 微博为: ' + wb.weibo[0]['overview'])
            print(u'最新/置顶 微博位置: ' + wb.weibo[0]['publish_place'])
            print(u'最新/置顶 微博发布时间: ' + wb.weibo[0]['publish_time'])
            print(u'最新/置顶 微博获得赞数: ' + str(wb.weibo[0]['up_num']))
            print(u'最新/置顶 微博获得转发数: ' + str(wb.weibo[0]['retweet_num']))
            print(u'最新/置顶 微博获得评论数: ' + str(wb.weibo[0]['comment_num']))
            print(u'最新/置顶 微博发布工具: ' + wb.weibo[0]['publish_tool'])
    except Exception as e:
        print('Error: ', e)
        traceback.print_exc()


if __name__ == '__main__':
    main()
