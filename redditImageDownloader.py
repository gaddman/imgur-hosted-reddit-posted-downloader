#! /usr/bin/env python

# fork of https://github.com/asweigart/imgur-hosted-reddit-posted-downloader
# works for python2 or python3
# explicitly creating session rather than requests.get so session can be closed on completion and avoid warnings of unclosed sockets (in python3)
import glob, logging, argparse, os
import praw, requests
from bs4 import BeautifulSoup

def downloadImage(imageUrl, localFileName):
    logging.debug('Download...')
    with requests.Session() as s:
        response = s.get(imageUrl, stream=True)
        size = float(response.headers['Content-Length'])/1024/1024    # determine file size in MB (where provided)
        logging.info('Downloading {} to {} ({:.2f}MB)...'.format(imageUrl,localFileName,size))
        if response.status_code == 200:
            with open(localFileName, 'wb') as fo:
                for chunk in response.iter_content(4096):
                    fo.write(chunk)

# define and parse arguments
parser = argparse.ArgumentParser()
parser = argparse.ArgumentParser(description="Download images from specified subreddit")
parser.add_argument ("subreddit", help="subreddit to download from", type=str)
parser.add_argument ("-d", "--downloadLocation", help="location to store downloads", default=".", type=str)
parser.add_argument ("-s", "--score", help="minimum score required to download", default=500, type=int)
parser.add_argument ("-l", "--logfile", help="filename for logging", type=str)
parser.add_argument ("-q", "--quiet", help="suppress output", action='store_true', default=False)
args = parser.parse_args()
downloadLocation=os.path.abspath(args.downloadLocation)

# setup logging to file and stderr
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
# suppress logs from the requests module hitting root logger
logging.getLogger('urllib3').propagate=False

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

logging.info('Beginning scrape of /r/{} subreddit (score>{}) to {}'.format(args.subreddit, args.score, downloadLocation))

# Connect to reddit and download the subreddit front page
r = praw.Reddit(user_agent='redditImageDownloader/1.0 (https://github.com/gaddman/redditImageDownloader)')
submissions = r.get_subreddit(args.subreddit).get_top_from_day(limit=25)

# Process all the submissions
try:
    for submission in submissions:
        # Check for all the cases where we will skip a submission:
        if submission.score < args.score:
            logging.info('Score too low ({}): "{}" at {}'.format(submission.score, submission.title, submission.url))
            continue # skip submissions that haven't even reached required score
        if len(glob.glob(os.path.join(downloadLocation,'reddit_%s_%s_*' % (args.subreddit, submission.id)))) > 0:
            logging.info('Already downloaded: "{}" at {}'.format(submission.title, submission.url))
            continue # we've already downloaded files for this reddit submission

        logging.info('Good submission (score {}): "{}" at {}'.format(submission.score, submission.title, submission.url))

        if '//imgur.com/a/' in submission.url:
            # This is an Imgur album submission.
            logging.debug('Imgur page album')
            with requests.Session() as s:
                response = s.get(submission.url)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text)
                    matches = soup.select('.album-view-image-link a')
                    logging.debug('--{} images'.format(len(matches)))
                    for match in matches:
                        imageUrl = match['href']
                        if imageUrl.startswith('//'):
                            # if no schema is supplied in the url, prepend 'http:' to it
                            imageUrl = 'http:' + imageUrl
                        imageFilename = imageUrl.split('/')[-1].split('#')[0].split('?')[0]
                        localFileName = os.path.join(downloadLocation,'reddit_%s_%s_%s' % (args.subreddit, submission.id, imageFilename))
                        downloadImage(imageUrl, localFileName)

        elif '//imgur.com/' in submission.url:
            # This is an Imgur page with a single image or a redirect to a single image
            logging.debug('Imgur page')
            # check for a redirection, using head rather than get
            with requests.Session() as s:
                response = s.head(submission.url, allow_redirects=False)
                if response.status_code == 301:
                    # redirected, grab where to (assuming imgur will only redirect once, with status 301)
                    logging.debug('--Imgur page redirect')
                    imageUrl = response.headers['location']
                elif response.status_code == 200:
                    # no redirect, go ahead and download the full page
                    logging.debug('--Imgur page single')
                    response = s.get(submission.url)
                    soup = BeautifulSoup(response.text)
                    imageUrl = soup.find('link', rel='image_src')['href']
                    if imageUrl.startswith('//'):
                        # if no schema is supplied in the url, prepend 'http:' to it
                        imageUrl = 'http:' + imageUrl

            imageFilename = imageUrl.split('/')[-1].split('#')[0].split('?')[0]
            localFileName = os.path.join(downloadLocation,'reddit_%s_%s_%s' % (args.subreddit, submission.id, imageFilename))
            downloadImage(imageUrl, localFileName)

        elif '//i.imgur.com/' in submission.url:
            # Imgur URL for single image
            logging.debug('Imgur image')
            imageUrl = submission.url
            imageFilename = imageUrl.split('/')[-1].split('#')[0].split('?')[0]
            localFileName = os.path.join(downloadLocation,'reddit_%s_%s_%s' % (args.subreddit, submission.id, imageFilename))
            downloadImage(imageUrl, localFileName)
        else:
            # non-Imgur URL, let's see what can be done.
            # Only interested in images, ignore redirects or links to HTML pages
            logging.debug('Non-imgur')
            with requests.Session() as s:
                response = s.head(submission.url)
                if 'image/' in response.headers['Content-Type']:
                    imageUrl = submission.url
                    imageFilename = imageUrl.split('/')[-1].split('#')[0].split('?')[0]
                    localFileName = os.path.join(downloadLocation,'reddit_%s_%s_%s' % (args.subreddit, submission.id, imageFilename))
                    downloadImage(imageUrl, localFileName)
                else:
                    logging.warning("'Content-Type' not suitable ({})".format(response.headers['Content-Type']))

    logging.info('Completed scrape')

except (praw.errors.InvalidSubreddit, praw.errors.RedirectException):
    logging.error("Invalid subreddit: {}".format(args.subreddit))