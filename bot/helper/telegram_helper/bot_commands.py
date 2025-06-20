# ruff: noqa: RUF012
from bot.core.config_manager import Config

i = Config.CMD_SUFFIX


class BotCommands:
    StartCommand = "start"
    MirrorCommand = [f"mirror{i}", f"m{i}"]
    JdMirrorCommand = [f"jdmirror{i}", f"jm{i}"]
    NzbMirrorCommand = [f"nzbmirror{i}", f"nm{i}"]
    YtdlCommand = [f"ytdl{i}", f"y{i}"]
    LeechCommand = [f"leech{i}", f"l{i}"]
    JdLeechCommand = [f"jdleech{i}", f"jl{i}"]
    NzbLeechCommand = [f"nzbleech{i}", f"nl{i}"]
    YtdlLeechCommand = [f"ytdlleech{i}", f"yl{i}"]
    CloneCommand = [f"clone{i}", f"c{i}"]
    MediaInfoCommand = [f"mediainfo{i}", f"mi{i}"]
    CountCommand = f"count{i}"
    DeleteCommand = f"del{i}"
    CancelAllCommand = f"cancelall{i}"
    ForceStartCommand = [f"forcestart{i}", f"fs{i}"]
    ListCommand = f"list{i}"
    SearchCommand = f"search{i}"
    HydraSearchCommand = f"nzbsearch{i}"
    StatusCommand = [f"status{i}", "statusall"]
    UsersCommand = f"users{i}"
    AuthorizeCommand = [f"auth{i}", f"a{i}"]
    UnAuthorizeCommand = [f"unauth{i}", f"ua{i}"]
    AddSudoCommand = f"addsudo{i}"
    RmSudoCommand = f"rmsudo{i}"
    PingCommand = f"ping{i}"
    RestartCommand = [f"restart{i}", "restartall"]
    StatsCommand = f"stats{i}"
    HelpCommand = f"help{i}"
    LogCommand = f"log{i}"
    ShellCommand = f"shell{i}"
    AExecCommand = f"aexec{i}"
    ExecCommand = f"exec{i}"
    ClearLocalsCommand = f"clearlocals{i}"
    BotSetCommand = [f"bsetting{i}", f"bs{i}"]
    UserSetCommand = [f"usetting{i}", f"us{i}"]
    SpeedTest = f"speedtest{i}"
    BroadcastCommand = [f"broadcast{i}", "broadcastall"]
    SelectCommand = f"sel{i}"
    RssCommand = f"rss{i}"
    SoxCommand = [f"spectrum{i}", f"sox{i}"]
