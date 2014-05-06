#! /usr/bin/env python

# fork of https://github.com/asweigart/imgur-hosted-reddit-posted-downloader
# works for python2 or python3
import argparse
import glob
import logging
import os

import requests
import praw
from bs4 import BeautifulSoup


def download_image(image_url, local_filename):
    """
    Download a given URL to a file
    """
    logging.debug('Download...')
    # explicitly creating session rather than requests.get so session can be closed on completion and avoid warnings of unclosed sockets (in python3)
    with requests.Session() as s:
        response = s.get(image_url, stream=True)
        # determine file size in MB (where provided)
        size = float(response.headers['Content-Length']) / 1024 / 1024
        logging.info('Downloading {} to {} ({:.2f}MB)...'.format(image_url, local_filename, size))
        if response.status_code == 200:
            with open(local_filename, 'wb') as fo:
                for chunk in response.iter_content(4096):
                    fo.write(chunk)


def imgur_handler(submission_url):
    """
    Download submissions in the Imgur domain.
    For a given Imgur URL, return a list of URLs to the images.
    Using BeautifulSoup rather than the Imgur API for now.
    """
    images = []
    if '//imgur.com/a/' in submission_url:
        # album
        logging.debug('Imgur page album')
        with requests.Session() as s:
            response = s.get(submission_url)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text)
                matches = soup.select('.album-view-image-link a')
                logging.debug('--{} images'.format(len(matches)))
                # for index, match in enumerate(matches):
                for index, match in enumerate(matches):
                    image_url = match['href']
                    if image_url.startswith('//'):
                        # if no schema is supplied in the url, prepend 'http:' to it
                        image_url = 'http:' + image_url
                    images.append(image_url)

    elif '//imgur.com/' in submission_url:
        # single image page or a redirect to a single image
        logging.debug('Imgur page')
        # check for a redirection, using head rather than get
        with requests.Session() as s:
            response = s.head(submission_url, allow_redirects=False)
            if response.status_code == 301:
                # redirected, grab where to (assuming imgur will only redirect once, with status 301)
                logging.debug('--Imgur page redirect')
                image_url = response.headers['location']
            elif response.status_code == 200:
                # no redirect, go ahead and download the full page
                logging.debug('--Imgur page single')
                response = s.get(submission_url)
                soup = BeautifulSoup(response.text)
                image_url = soup.find('link', rel='image_src')['href']
                if image_url.startswith('//'):
                    # if no schema is supplied in the url, prepend 'http:' to it
                    image_url = 'http:' + image_url
                images.append(image_url)

    elif '//i.imgur.com/' in submission_url:
        # single image, no magic needed
        logging.debug('Imgur image')
        images.append(submission_url)

    return images


def reddit_image_downloader(subreddit, period='day', score=500, max=25, download_location='.'):
    """
    Download images from a chosen Reddit subreddit
    """

    logging.info('Beginning scrape of /r/{} subreddit (top this {}, score>{}) to {}'.format(
        subreddit, period, score, download_location))

    # Connect to reddit and download the subreddit front page
    r = praw.Reddit(user_agent='redditImageDownloader/1.2 (https://github.com/gaddman/redditImageDownloader)')
    if period == 'day':
        submissions = r.get_subreddit(subreddit).get_top_from_day(limit=max)
    elif period == 'week':
        submissions = r.get_subreddit(subreddit).get_top_from_week(limit=max)
    elif period == 'month':
        submissions = r.get_subreddit(subreddit).get_top_from_month(limit=max)

    # Process all the submissions
    try:
        for submission in submissions:
            # Check for all the cases where we will skip a submission:
            if submission.score < score:
                logging.info('Score too low ({}): "{}" at {}'.format(submission.score, submission.title, submission.url))
                continue  # skip submissions that haven't even reached required score
            if len(glob.glob(os.path.join(download_location, 'reddit_{}_{}_*'.format(subreddit, submission.id)))) > 0:
                logging.info('Already downloaded: "{}" at {}'.format(submission.title, submission.url))
                continue  # we've already downloaded files for this reddit submission

            logging.info('Good submission (score {}): "{}" at {}'.format(submission.score, submission.title, submission.url))

            if 'imgur.com/' in submission.url:
                # This is an Imgur submission, we can deal with this
                image_urls = imgur_handler(submission.url)
                for index, image_url in enumerate(image_urls):
                    image_filename = image_url.split('/')[-1].split('#')[0].split('?')[0]
                    local_filename = 'reddit_{}_{}_{:02d}_{}'.format(subreddit, submission.id, index, image_filename)
                    download_image(image_url, os.path.join(download_location, local_filename))
            else:
                # non-Imgur URL, let's see what can be done.
                # Only interested in images, ignore redirects or links to HTML pages
                logging.debug('Non-imgur')
                with requests.Session() as s:
                    response = s.head(submission.url)
                    if 'image/' in response.headers['Content-Type']:
                        image_url = submission.url
                        image_filename = image_url.split('/')[-1].split('#')[0].split('?')[0]
                        local_filename = 'reddit_{}_{}_{}'.format(subreddit, submission.id, image_filename)
                        download_image(image_url, os.path.join(download_location, local_filename))
                    else:
                        logging.warning("'Content-Type' not suitable ({})".format(response.headers['Content-Type']))

        logging.info('Completed scrape')

    except (praw.errors.InvalidSubreddit, praw.errors.RedirectException):
        logging.error("Invalid subreddit: {}".format(subreddit))


def getargs():
    """
    Just grab all the command line arguments and return
    """
    parser = argparse.ArgumentParser()
    parser = argparse.ArgumentParser(description="Download images from specified Reddit subreddit")
    parser.add_argument("subreddit", help="subreddit to download from", type=str)
    parser.add_argument("-p", "--period", help="period of interest (day, week, month)", default="day", type=str)
    parser.add_argument("-s", "--score", help="minimum score required to download", default=500, type=int)
    parser.add_argument("-d", "--download_location", help="location to store downloaded images", default=".", type=str)
    parser.add_argument("-l", "--logfile", help="filename for logging", type=str)
    parser.add_argument("-m", "--max", help="maximum number of submissions", default=25, type=int)
    parser.add_argument("-q", "--quiet", help="suppress output", action='store_true', default=False)
    args = parser.parse_args()
    args.download_location = os.path.abspath(args.download_location)

    return args


if __name__ == '__main__':
    args = getargs()

    # setup logging to file and stderr
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    # suppress logs from the requests module hitting root logger
    logging.getLogger('urllib3').propagate = False

    if args.logfile:
        fh = logging.FileHandler(filename=args.logfile)
        formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(name)s %(message)s')
        fh.setFormatter(formatter)
        fh.setLevel(logging.DEBUG)
        logger.addHandler(fh)
        logging.getLogger('urllib3').addHandler(fh)

    if not args.quiet:
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        logger.addHandler(ch)

    reddit_image_downloader(args.subreddit, args.period, args.score, args.max, args.download_location)