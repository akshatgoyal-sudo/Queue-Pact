"""UTF-8 CSV exports; display formatting never changes stored numbers."""
import csv
import io
import json
import zipfile
from .models import Policy


def safe_cell(value):
    if value is None:
        return ''
    if isinstance(value,(dict,list)):
        value=json.dumps(value,ensure_ascii=False,allow_nan=False)
    if isinstance(value,str) and (value.startswith(('\t','\r','\n')) or value.lstrip().startswith(('=','+','-','@'))):
        return "'"+value
    return value


def csv_bytes(rows,columns):
    stream=io.StringIO(newline='')
    writer=csv.writer(stream)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([safe_cell(row.get(c)) for c in columns])
    return stream.getvalue().encode('utf-8-sig')


def csv_zip(evidence):
    d=evidence.data
    metrics=[]; students=[]; actions=[]; resources=[]
    for r in d['runs']:
        for key,value in r['metrics'].items():
            if isinstance(value,(list,dict)):
                continue
            unit='count' if key in ('arrived','completed','unfinished','not_arrived','waiting','in_service','preparing') else 'student-minutes' if key in ('total_queue_wait','unfinished_wait') else 'minutes' if any(x in key for x in ('wait','visit','makespan','window')) else 'text'
            metrics.append(dict(run=r['label'],policy=Policy(r['record']['policy']).label,policy_identifier=r['record']['policy'],policy_version=Policy(r['record']['policy']).algorithm_version,metric=key,value=value,unit=unit,observation_min=r['observation_min'],experiment_status=d['status']))
        students.extend(dict(run=r['label'],**s) for s in r['students'])
        actions.extend(dict(run=r['label'],action_id=a['id'],time_min=a['time'],kind=a['kind'],counter_id=a['counter_id'],payload_json=a['payload_json'],after_boundary=a['at_boundary']) for a in r['actions'])
        resources.extend(dict(run=r['label'],counter_id=c['id'],service=c['service'],staff_id=c['staff_id'],busy_min=dict(r['metrics']['counter_busy_time'])[c['id']],utilization=dict(r['metrics']['counter_utilization'])[c['id']]) for c in r['resources'])
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for filename,rows,columns in [
            ('metrics.csv',metrics,['run','policy','policy_identifier','policy_version','metric','value','unit','observation_min','experiment_status']),
            ('students.csv',students,['run','student_id','status','arrival_min','finished_min','queue_wait_min','preparation_min','visit_min','completed_tasks']),
            ('actions.csv',actions,['run','action_id','time_min','kind','counter_id','payload_json','after_boundary']),
            ('resources.csv',resources,['run','counter_id','service','staff_id','busy_min','utilization'])]:
            z.writestr(filename,csv_bytes(rows,columns))
        candidates=d['settings'].get('staff_outcomes')
        if candidates:
            rows=[dict(placement=c['placement'],completed=c['completed'],unfinished=c['unfinished'],total_queue_wait_student_min=c['total_wait'],average_completed_wait_min=c['average_wait']) for c in candidates]
            z.writestr('staff_candidates.csv',csv_bytes(rows,['placement','completed','unfinished','total_queue_wait_student_min','average_completed_wait_min']))
    return output.getvalue()
