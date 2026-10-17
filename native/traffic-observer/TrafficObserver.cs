// Local ETW network byte counters. No packet payloads, filters or routing changes.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net;
using System.Security.Principal;
using System.Threading;
using System.Web.Script.Serialization;
using Microsoft.Diagnostics.Tracing.Parsers;
using Microsoft.Diagnostics.Tracing.Session;

class Flow {
    public string protocol, local, remote;
    public int pid, local_port, remote_port;
    public long sent, received;
    public double first, last;
}

class TrafficObserver {
    static readonly object Gate = new object();
    static readonly Dictionary<string, Flow> Flows = new Dictionary<string, Flow>();
    static string Output;
    static readonly double Started = Now();
    static double Now() { return (DateTime.UtcNow - new DateTime(1970,1,1)).TotalSeconds; }
    static void Add(string protocol, int pid, int size, IPAddress source, int sport, IPAddress target, int dport, bool send, double time) {
        if(pid <= 0 || size <= 0) return;
        // TCP events describe the connection's local/remote endpoints in both
        // directions. UDP events describe the packet's source/destination.
        bool localIsSource = protocol == "TCP" || send;
        string local = (localIsSource ? source : target).ToString(), remote = (localIsSource ? target : source).ToString();
        int localPort = localIsSource ? sport : dport, remotePort = localIsSource ? dport : sport;
        string key = protocol + "|" + pid + "|" + local + "|" + localPort + "|" + remote + "|" + remotePort;
        lock(Gate) {
            Flow flow;
            if(!Flows.TryGetValue(key,out flow)) {
                flow = new Flow { protocol=protocol, pid=pid, local=local, local_port=localPort, remote=remote, remote_port=remotePort, first=time };
                Flows.Add(key, flow);
            }
            if(send) flow.sent += size; else flow.received += size;
            flow.last = time;
        }
    }
    static void Save(string status, int parent, long lost, string error = "") {
        try {
            string json;
            lock(Gate) {
                foreach(var key in Flows.Where(p => p.Value.last < Now()-900).Select(p=>p.Key).ToArray()) Flows.Remove(key);
                json = new JavaScriptSerializer { MaxJsonLength=16*1024*1024 }.Serialize(new { schema=2, status=status, viewer_pid=parent, started=Started, updated=Now(), lost_events=lost, error=error, flows=Flows.Values.ToArray() });
            }
            string temp=Output+".tmp";
            File.WriteAllText(temp,json);
            if(File.Exists(Output)) File.Replace(temp,Output,null); else File.Move(temp,Output);
        } catch(IOException) {} catch(UnauthorizedAccessException) {}
    }
    static int Main(string[] args) {
        if(args.Length==1 && args[0]=="--self-test") {
            Add("TCP",123,100,IPAddress.Loopback,5000,IPAddress.Parse("1.1.1.1"),443,true,1);
            Add("TCP",123,300,IPAddress.Loopback,5000,IPAddress.Parse("1.1.1.1"),443,false,2);
            var flow=Flows.Values.Single();
            return flow.sent==100 && flow.received==300 && flow.local_port==5000 ? 0 : 1;
        }
        int parent;
        if((args.Length!=1 && args.Length!=2) || !int.TryParse(args[0],out parent)) return 2;
        Output = args.Length==2 ? Path.GetFullPath(args[1]) : Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "..", "state", "traffic.json"));
        if(!new WindowsPrincipal(WindowsIdentity.GetCurrent()).IsInRole(WindowsBuiltInRole.Administrator)) { Save("admin_required",parent,0); return 3; }
        try {
            var owner=Process.GetProcessById(parent);
            DateTime ownerStarted=owner.StartTime;
            using(var session=new TraceEventSession("XrayConnectionsTraffic_"+parent)) {
                session.StopOnDispose=true;
                session.EnableKernelProvider(KernelTraceEventParser.Keywords.NetworkTCPIP);
                var kernel=session.Source.Kernel;
                kernel.TcpIpSend += e => Add("TCP",e.ProcessID,e.size,e.saddr,e.sport,e.daddr,e.dport,true,Now());
                kernel.TcpIpRecv += e => Add("TCP",e.ProcessID,e.size,e.saddr,e.sport,e.daddr,e.dport,false,Now());
                kernel.UdpIpSend += e => Add("UDP",e.ProcessID,e.size,e.saddr,e.sport,e.daddr,e.dport,true,Now());
                kernel.UdpIpRecv += e => Add("UDP",e.ProcessID,e.size,e.saddr,e.sport,e.daddr,e.dport,false,Now());
                kernel.TcpIpSendIPV6 += e => Add("TCP",e.ProcessID,e.size,e.saddr,e.sport,e.daddr,e.dport,true,Now());
                kernel.TcpIpRecvIPV6 += e => Add("TCP",e.ProcessID,e.size,e.saddr,e.sport,e.daddr,e.dport,false,Now());
                kernel.UdpIpSendIPV6 += e => Add("UDP",e.ProcessID,e.size,e.saddr,e.sport,e.daddr,e.dport,true,Now());
                kernel.UdpIpRecvIPV6 += e => Add("UDP",e.ProcessID,e.size,e.saddr,e.sport,e.daddr,e.dport,false,Now());
                Save("running",parent,0);
                using(var timer=new Timer(_ => {
                    bool alive;
                    try { alive=!owner.HasExited && owner.StartTime==ownerStarted; } catch { alive=false; }
                    if(!alive) { session.Dispose(); return; }
                    Save("running",parent,session.Source.EventsLost);
                },null,1000,1000)) session.Source.Process();
                Save("stopped",parent,session.Source.EventsLost);
            }
            return 0;
        } catch(Exception error) { Save("error",parent,0,error.Message); return 1; }
    }
}
