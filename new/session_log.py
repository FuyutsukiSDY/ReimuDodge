"""Bounded asynchronous diagnostics with observable flush progress."""
import json,queue,threading,time

class SessionLog:
    def __init__(self,path,capacity=128):
        self.path=path;self.queue=queue.Queue(capacity);self.closed=threading.Event()
        self.dropped=0;self.error=None;self.submitted=0;self.written=0;self.flushed=0;self.rejected=0
        self.thread=threading.Thread(target=self.run,name='session-log',daemon=True)
        self.thread.start()

    def health(self):
        return dict(path=str(self.path),submitted=self.submitted,written=self.written,flushed=self.flushed,
                    rejected=self.rejected,dropped=self.dropped,pending=self.queue.qsize(),
                    error=self.error,closed=self.closed.is_set(),alive=self.thread.is_alive())

    def submit(self,record):
        if self.closed.is_set() or self.error:
            self.rejected+=1;return False
        try:self.queue.put_nowait(record)
        except queue.Full:
            self.dropped+=1;return False
        self.submitted+=1
        return True

    def run(self):
        try:
            with self.path.open('a',encoding='utf8') as f:
                flushed=time.monotonic()
                while not self.closed.is_set() or not self.queue.empty():
                    try:r=self.queue.get(timeout=.1)
                    except queue.Empty:pass
                    else:
                        try:
                            f.write(json.dumps(r,default=lambda v:v.tolist())+'\n')
                            self.written+=1
                        finally:self.queue.task_done()
                    if (self.written==1 and self.flushed==0) or time.monotonic()-flushed>=1:
                        f.flush();self.flushed=self.written;flushed=time.monotonic()
                f.flush();self.flushed=self.written
        except Exception as e:self.error=repr(e)

    def close(self):
        self.closed.set();self.thread.join(timeout=2)
