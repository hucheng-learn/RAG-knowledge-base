# Run from any directory after the upstream images are available locally.
$ErrorActionPreference = 'Stop'

$images = @(
    @{ Source = 'mysql:8.0'; Target = 'rag-mysql:rag-8.0' },
    @{ Source = 'quay.io/coreos/etcd:v3.5.14'; Target = 'rag-etcd:rag-v3.5.14' },
    @{ Source = 'minio/minio:RELEASE.2023-03-20T20-16-18Z'; Target = 'rag-minio:rag-RELEASE.2023-03-20T20-16-18Z' },
    @{ Source = 'milvusdb/milvus:v2.4.13'; Target = 'rag-milvus:rag-v2.4.13' },
    @{ Source = 'ollama/ollama:latest'; Target = 'rag-ollama:rag-latest' },
    @{ Source = 'mineru:4'; Target = 'rag-mineru:rag-4' }
)

foreach ($image in $images) {
    docker image inspect $image.Source *> $null
    if ($LASTEXITCODE -ne 0) {
        docker image inspect $image.Target *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Already available: $($image.Target)"
            continue
        }
        throw "Missing $($image.Source). Pull or build it first, then rerun this script."
    }

    docker tag $image.Source $image.Target
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to tag $($image.Source) as $($image.Target)."
    }
    Write-Host "$($image.Source) -> $($image.Target)"
}
