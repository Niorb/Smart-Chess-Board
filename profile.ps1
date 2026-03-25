function Start-ChessSync {
    mutagen sync create --name=smartChessBoard "C:\Users\robin\Bureau\Smart Chess Board\Raspberry" robin@192.168.0.239:~/chess
}
Set-Alias -Name chesssync -Value Start-ChessSync
function Stop-ChessSync { mutagen sync terminate smartChessBoard }
function Show-ChessSync { mutagen sync monitor smartChessBoard }
Set-Alias -Name chessstop -Value Stop-ChessSync
Set-Alias -Name chessmon -Value Show-ChessSync