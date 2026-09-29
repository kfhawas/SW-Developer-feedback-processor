import sys, os, json, datetime, re
import csv

# customer feedback processor
# usage: python process_feedback.py file1.csv file2.csv ...

POSITIVE = ['great','good','love','excellent','happy','fast','helpful','amazing','easy','friendly']
NEGATIVE = ['bad','slow','terrible','hate','broken','rude','late','poor','difficult','refund']
STOPWORDS = ['the','a','an','and','or','but','is','was','it','to','of','in','for','on','with','my','i','me','this','that','very','so','they','we','you','not','be','have','had','at','are','were','as','our','your','their','from','just','too','again','all','no']

allRows = []
fiveStar = 0

def getSentiment(text, pos=POSITIVE, neg=NEGATIVE):
    score = 0
    text = text.lower()
    for w in pos:
        if w in text:
            score = score + 1
    for w in neg:
        if w in text:
            score = score - 1
    if score > 0: return score, 'positive'
    elif score < 0: return score, 'negative'
    else: return score, 'neutral'

def countWords(text, counts={}):
    text = re.sub('[^\w\s]', '', text.lower())
    for w in text.split():
        if w not in STOPWORDS:
            if w in counts:
                counts[w] = counts[w] + 1
            else:
                counts[w] = 1
    return counts

def processFile(fname):
    global fiveStar
    f = open(fname)
    lines = f.readlines()
    header = lines[0].strip().split(',')
    for i in range(1, len(lines)-1):
        parts = lines[i].strip().split(',')
        row = dict(zip(header, parts))
        rating = int(row['rating'])
        d = datetime.datetime.strptime(row['date'], '%Y-%m-%d')
        s, label = getSentiment(row['comment'])
        if rating is 5:
            fiveStar = fiveStar + 1
        allRows.append({'id': row['id'], 'date': d.strftime('%Y-%m-%d'), 'customer': row['customer'], 'channel': row['channel'].lower(), 'rating': rating, 'comment': row['comment'], 'sentiment_score': s, 'sentiment': label})
    print("read " + str(len(allRows)) + " rows from " + fname)

def main():
    files = sys.argv[1:]
    if len(files) == 0:
        print("no files given")
        return
    for fn in files:
        processFile(fn)

    # averages
    total = 0
    for r in allRows:
        total = total + r['rating']
    avg = total // len(allRows)

    channels = []
    for r in allRows:
        if r['channel'] not in channels:
            channels.append(r['channel'])
    chanAvg = {}
    for c in channels:
        t = 0
        n = 0
        for r in allRows:
            if r['channel'] == c:
                t = t + r['rating']
                n = n + 1
        chanAvg[c] = t // n

    sentCounts = {'positive': 0, 'negative': 0, 'neutral': 0}
    for r in allRows:
        sentCounts[r['sentiment']] += 1

    counts = {}
    for r in allRows:
        counts = countWords(r['comment'])
    top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:10]

    followUp = []
    for r in allRows:
        if r['rating'] < 2:   # flag 1 and 2 star reviews for follow up
            followUp.append(r['id'])

    # write processed rows
    out = "id,date,customer,channel,rating,comment,sentiment_score,sentiment\n"
    for r in allRows:
        out = out + r['id'] + "," + r['date'] + "," + r['customer'] + "," + r['channel'] + "," + str(r['rating']) + "," + r['comment'] + "," + str(r['sentiment_score']) + "," + r['sentiment'] + "\n"
    f = open("output/processed_feedback.csv", "w")
    f.write(out)

    summary = {'total': len(allRows), 'average_rating': avg, 'channel_averages': chanAvg, 'sentiment_counts': sentCounts, 'five_star_count': fiveStar, 'top_keywords': top, 'follow_up_ids': followUp}
    json.dump(summary, open("output/summary.json", "w"), indent=2)
    print("done")

main()
