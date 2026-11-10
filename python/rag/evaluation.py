"""Reproducible retrieval evaluation in a separate temporary SQLite database."""
import json,tempfile,time,hashlib,math,statistics
from pathlib import Path
from datetime import datetime,timezone
from .library import initialize,search
from community.db import database

def evaluate():
    file=Path(__file__).with_name('eval_cases.json');raw=file.read_bytes();dataset=json.loads(raw)
    output={'dataset':dataset['version'],'description':dataset['description'],'dataset_sha256':hashlib.sha256(raw).hexdigest(),
        'created_at':datetime.now(timezone.utc).isoformat(),'k':3,'cases':len(dataset['cases']),'strategies':{}}
    with tempfile.TemporaryDirectory(prefix='travel-rag-eval-') as folder:
        db=Path(folder)/'eval.sqlite3';initialize(db)
        with database(db) as conn:
            docs=[dict(r) for r in conn.execute('SELECT id,title,city,body FROM knowledge_docs ORDER BY id')]
        corpus=json.dumps(docs,ensure_ascii=False,sort_keys=True).encode()
        output['corpus_sha256']=hashlib.sha256(corpus).hexdigest();output['documents']=len(docs)
        known={d['id'] for d in docs}
        for strategy in ['bm25','hybrid']:
            rows=[]
            for case in dataset['cases']:
                started=time.perf_counter();hits=search(case['query'],case['city'],3,strategy=strategy,db_path=db)
                elapsed=(time.perf_counter()-started)*1000
                retrieved=[h['id'].rsplit(':',1)[0] for h in hits];expected=set(case['relevant_doc_ids'])
                relevance=[int(d in expected) for d in retrieved]
                rank=next((i+1 for i,x in enumerate(relevance) if x),None)
                idcg=sum(1/math.log2(i+2) for i in range(min(3,len(expected))))
                rows.append({'id':case['id'],'split':case['split'],'query':case['query'],'expected':sorted(expected),'retrieved':retrieved,
                    'recall':len(set(retrieved)&expected)/len(expected) if expected else None,'mrr':1/rank if rank else 0,
                    'ndcg':sum(r/math.log2(i+2) for i,r in enumerate(relevance))/idcg if idcg else None,
                    'abstained':not retrieved,'citation_ids_valid':all(d in known for d in retrieved),'elapsed_ms':round(elapsed,3)})
            def aggregate(items):
                positives=[r for r in items if r['expected']];negative=[r for r in items if not r['expected']]
                return {'count':len(items),'recall_at_3':round(statistics.mean(r['recall'] for r in positives),4) if positives else None,
                    'mrr_at_3':round(statistics.mean(r['mrr'] for r in positives),4) if positives else None,
                    'ndcg_at_3':round(statistics.mean(r['ndcg'] for r in positives),4) if positives else None,
                    'negative_abstention_rate':round(statistics.mean(r['abstained'] for r in negative),4) if negative else None,
                    'citation_id_validity':statistics.mean(r['citation_ids_valid'] for r in items) if items else None,
                    'p50_retrieval_ms':round(statistics.median(r['elapsed_ms'] for r in items),3) if items else None}
            output['strategies'][strategy]={'overall':aggregate(rows),'splits':{split:aggregate([r for r in rows if r['split']==split]) for split in ['development','regression','negative']},'details':rows}
    output['limitations']=['固定人工合成检索集，不代表真实用户表现','引用ID有效不等于内容支持答案','本次不评测模型回答正确率，不调用付费模型','hybrid 使用稀疏字符TF-IDF，不是神经语义向量模型']
    return output

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='rag_eval_report.json');args=parser.parse_args()
    report=evaluate();Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({s:r['overall'] for s,r in report['strategies'].items()},ensure_ascii=False,indent=2))
