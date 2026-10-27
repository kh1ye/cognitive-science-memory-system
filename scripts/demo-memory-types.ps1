param(
    [ValidatePattern('^[A-Za-z0-9_-]{1,100}$')]
    [string]$UserId = 'meeting-demo-20261021-types',
    [string]$BaseUrl = 'http://127.0.0.1:8765'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$apiRoot = $BaseUrl.TrimEnd('/')
$encodedUser = [Uri]::EscapeDataString($UserId)

# Keep this source file ASCII-only so Windows PowerShell 5.1 can parse it
# regardless of the active ANSI code page. Demo text is decoded as UTF-8.
function ConvertFrom-Base64Utf8 {
    param(
        [Parameter(Mandatory)]
        [string]$Value
    )

    return [System.Text.Encoding]::UTF8.GetString(
        [System.Convert]::FromBase64String($Value)
    )
}

$health = Invoke-RestMethod -Uri "$apiRoot/api/health"
if ($health.status -ne 'ok') {
    throw 'API health check failed.'
}

$existing = Invoke-RestMethod -Uri "$apiRoot/api/memories?user_id=$encodedUser&limit=1"
if (@($existing.items).Count -gt 0) {
    throw "User space '$UserId' already contains memories. Use a new UserId."
}

$examples = @(
    [ordered]@{
        label = 'Semantic'
        expected_type = 'semantic'
        expected_role = 'current'
        payload = [ordered]@{
            user_id = $UserId
            content = ConvertFrom-Base64Utf8 '5oiR55qE6ZW/5pyf56CU56m25pa55ZCR5piv6K6k55+l56eR5a2m5Lit55qE6K6w5b+G5bu65qih44CC'
            memory_key = 'research_direction'
            memory_value = ConvertFrom-Base64Utf8 '6K6k55+l56eR5a2m6K6w5b+G5bu65qih'
            memory_type = 'semantic'
            source = 'meeting_demo'
            tags = @('profile', 'fact')
            importance = 0.85
            confidence = 0.95
        }
    }
    [ordered]@{
        label = 'Episodic'
        expected_type = 'episodic'
        expected_role = 'current'
        payload = [ordered]@{
            user_id = $UserId
            content = ConvertFrom-Base64Utf8 'MjAyNiDlubQgMTAg5pyIIDIxIOaXpeS4iuWNiO+8jOaIkeWcqOe7hOS8muS4iuesrOS4gOasoeWujOaVtOa8lOekuuS6humVv+acn+iusOW/huezu+e7n++8jOW5tuiusOW9leS6huiAgeW4iOaPkOWHuueahOS/ruaUueW7uuiuruOAgg=='
            memory_key = 'meeting_demo_event_20261021'
            memory_value = ConvertFrom-Base64Utf8 '5a6M5oiQ6aaW5qyh5a6M5pW05ryU56S65bm25pS25Yiw5L+u5pS55bu66K6u'
            memory_type = 'episodic'
            source = 'meeting_demo'
            tags = @('event', 'timeline')
            importance = 0.82
            confidence = 0.95
        }
    }
    [ordered]@{
        label = 'Procedural'
        expected_type = 'procedural'
        expected_role = 'current'
        payload = [ordered]@{
            user_id = $UserId
            content = ConvertFrom-Base64Utf8 '5oiR5pW055CG5a6e6aqM5pWw5o2u5pe277yM6YCa5bi45YWI5qOA5p+l5bm25aSE55CG57y65aSx5YC877yM5YaN6L+Q6KGM5YiG5p6Q6ISa5pys77yM5pyA5ZCO5qC45a+557uf6K6h57uT5p6c5ZKM5Zu+6KGo44CC'
            memory_key = 'experiment_data_workflow'
            memory_value = ConvertFrom-Base64Utf8 '5qOA5p+l57y65aSx5YC8IC0+IOi/kOihjOWIhuaekCAtPiDmoLjlr7nnu5Pmnpw='
            memory_type = 'procedural'
            source = 'meeting_demo'
            tags = @('procedure', 'workflow')
            importance = 0.88
            confidence = 0.95
        }
    }
)

$results = foreach ($example in $examples) {
    $json = $example.payload | ConvertTo-Json -Depth 6 -Compress
    $response = Invoke-RestMethod `
        -Method Post `
        -Uri "$apiRoot/api/memories" `
        -ContentType 'application/json; charset=utf-8' `
        -Body ([System.Text.Encoding]::UTF8.GetBytes($json))
    $memory = $response.memory
    if ($memory.memory_type -ne $example.expected_type) {
        throw "$($example.label) type mismatch: $($memory.memory_type)"
    }
    if ($memory.state_role -ne $example.expected_role) {
        throw "$($example.label) state mismatch: $($memory.state_role)"
    }
    [pscustomobject]@{
        Example = $example.label
        Decision = $response.decision
        MemoryType = $memory.memory_type
        StateRole = $memory.state_role
        Content = $memory.content
    }
}

$results | Format-Table -AutoSize -Wrap
Write-Host "`nAll three memory types were written to user space: $UserId" -ForegroundColor Green
Write-Host 'Open Memory Management in the web UI and select each type tab.'
