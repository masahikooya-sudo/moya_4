# 運用手順(IDCFクラウド コンテナ)

IDCFクラウド コンテナ(SUSE Rancher/RKE2ベースのマネージドKubernetes)上で、
本アプリを起動・停止・更新・削除するための手順をまとめる。
マニフェスト自体の内容や初回セットアップの前提条件は `../README.md` の
「Kubernetes(IDCFクラウド等)」セクションを参照(イメージのビルド・プッシュ、
Secretの作成、ドメイン設定など)。

## 0. 前提: kubectlの接続確認

IDCFクラウド コンテナのコンソールで対象クラスターのダッシュボードを開き、
上部メニューの「KubeConfigをダウンロード」からkubeconfigファイルを取得する。
ダウンロードされるkubeconfigには2種類のcontextが含まれる。

- コンソールを **経由して** 接続するcontext(社内ネットワーク等を問わず使える)
- コンソールを **経由せず** 直接クラスターへ接続するcontext(低遅延だが、
  クラスターへの直接到達性が必要)

どちらを使うかは `kubectl config get-contexts` / `kubectl config use-context <name>`
で切り替えられる。まずは以下で疎通を確認する。

```bash
export KUBECONFIG=/path/to/downloaded-kubeconfig.yaml
kubectl get nodes
```

## 1. 起動(初回デプロイ)

`README.md` の手順1〜5(イメージのビルド・プッシュ、レジストリSecret作成、
`kustomization.yaml` の書き換え、Google認証情報Secretの作成、ドメイン設定)を
済ませたうえで、以下を実行する。

```bash
kubectl apply -k k8s/
kubectl -n pii-masking-shield rollout status deployment/moya4
```

`rollout status` が `deployment "moya4" successfully rolled out` と表示されれば
起動完了。Presidio/spaCyモデルの読み込みに数十秒かかることがあるが、
`startupProbe` がこれを待つよう設定済みなので、Podが `Running` になった後
自動的に受付可能な状態へ遷移する。

```bash
kubectl -n pii-masking-shield get pods
kubectl -n pii-masking-shield logs -f deployment/moya4
```

Ingressの `ADDRESS` にILBのアドレスが割り当てられたら、`masking.pdpro.jp` の
DNS(Aレコード)をそのアドレスへ向け、TLS証明書の初回annotation付与(下記)を
済ませれば `https://masking.pdpro.jp/` でアクセスできる。

```bash
kubectl -n pii-masking-shield get ingress moya4
```

> ILBはVPN経由でのみ到達できるプライベート構成を前提にしている(既定)。
> インターネットから直接アクセスさせる場合は、`k8s/ingress.yaml` の
> `ilb.idcfcloud.com/public-ipaddress-assignment: "true"` のコメントを外して
> パブリックIPを割り当てる。

未設定の段階で先に動作だけ確認したい場合はポートフォワードを使う。

```bash
kubectl -n pii-masking-shield port-forward svc/moya4 8000:80
```

### ILB(Infinite LB)との連携について

IDCFクラウド コンテナには、nginx等の汎用Ingress Controllerではなく、
**独自のIngressClass**が用意されている(確認環境では `idcf-ilb`、
コントローラーは `idcfcloud.com/idcf-ingress`)。以下で確認する。

```bash
kubectl get ingressclass
```

表示された名前を、`k8s/ingress.yaml` の `ingressClassName` に設定する
(既定では `idcf-ilb` にしてあるが、環境によって名前が異なる可能性がある)。
この方式では、Ingress ControllerのServiceを探して手動でannotationを
付与するといった作業は不要で、正しいIngressClassを指定するだけで
ILBとの連携が行われる。

`k8s/service-loadbalancer.example.yaml`(Ingressを経由せずServiceに直接ILBを
紐づける方式)は、TLS証明書の自動更新(下記のidcf-dns-certbot)と組み合わせられない
ため、使わないこと(IDCFクラウドのガイドに、Service型ILBで証明書を指定する
annotationの記載が無い)。

### TLS証明書(idcf-dns-certbotによる自動更新)

TLSはILBで終端する(アノテーション方式)。証明書の取得・更新は
[kojiaki131/idcf-dns-certbot](https://github.com/kojiaki131/idcf-dns-certbot)
(`cert-renew` namespaceで動くCronJob)に任せる。certbotはDNS-01検証で
`*.pdpro.jp` 等のLet's Encrypt証明書を取得・更新し、更新のたびに

1. 証明書をILBへアップロードし(`idcfcloud ilb upload_sslcert`)、
2. このアプリのIngressの `ilb.idcfcloud.com/sslcert-id` annotationを新しい証明書IDに差し替える。

そのため、このアプリ側でTLS Secret(`moya4-tls`)を作る必要は無く、
`k8s/ingress.yaml` にも `tls:` ブロックは書いていない。

(cert-manager経由のLet's Encrypt(HTTP-01検証)は、このクラスタでは使えないことを
実機で確認済み。cert-managerが検証用に自動生成する一時Ingress(ルート`/`パスを
持たない)を、IDCF独自の管理Webhook(`validate-idcf-ingress.idcfcloud.com`)が
「defaultBackendまたは`/`パスのルールが必要」として拒否するため。)

#### idcf-dns-certbot側の設定

idcf-dns-certbotのREADMEの手順に従って構築し、次の値をこのアプリに合わせる。

| ファイル | 設定 |
|---|---|
| `k8s/cronjob.yaml` | `CERT_DOMAIN: "*.pdpro.jp"`(`masking.pdpro.jp` を含む証明書) |
| `k8s/cronjob.yaml` | `INGRESS_TARGETS: "pii-masking-shield/moya4"` |
| `k8s/rbac.yaml` | Role/RoleBindingの `namespace: pii-masking-shield`、`resourceNames: [moya4]` |

#### 初回だけ: 証明書IDをIngressへ付与する

certbotがIngressを書き換えるのは、証明書が実際に更新されたときだけ
(有効期限が近づいたとき)。Ingressを新しく作った直後は、現在の証明書IDを
手動で1回だけ付与する。証明書IDは、certbotのJobログの
`sslcert-idを...に変更します` の行、または `idcfcloud ilb list_sslcerts --profile ilb`
で確認できる。

```bash
kubectl -n pii-masking-shield annotate ingress moya4 \
  ilb.idcfcloud.com/sslcert-id=<現在のsslcert-id> --overwrite
```

**`ilb.idcfcloud.com/sslcert-id` は `k8s/ingress.yaml` に書かないこと。**
固定値で書くと、certbotが更新した後に `kubectl apply -k k8s/` を実行した時点で
古い証明書IDへ巻き戻ってしまう(`kubectl annotate` で付けたannotationは、
マニフェストに書いていなければ `kubectl apply` しても消えない)。

Ingressを削除して作り直した場合(`kubectl delete -k k8s/` 後の再デプロイ等)も、
annotationが消えるので上記を再実行する。

現在の値は次で確認できる。

```bash
kubectl -n pii-masking-shield get ingress moya4 \
  -o jsonpath='{.metadata.annotations.ilb\.idcfcloud\.com/sslcert-id}'
```

### SSLポリシー(IDCFクラウド固有)の設定

IDCFクラウドのIngressでHTTPSを使う場合、事前にIDCFクラウド コンソール
でSSLポリシーを発行し、そのIDを `k8s/ingress.yaml` の
`ilb.idcfcloud.com/sslpolicy-id` annotationに設定する必要がある
(実機で確認済み。`k8s/ingress.yaml` には設定済みのSSLポリシーIDが入っている)。
これが無い、または値が誤っていると、Ingressの`ADDRESS`が割り当てられず
LBの生成に失敗する。

```bash
kubectl -n pii-masking-shield describe ingress moya4
# Warning Error ... generateLB failed: ...
# "ilb.idcfcloud.com/sslpolicy-id" annotation is not found
# と表示される場合、上記annotationが未設定または値が誤っている。
```

> **未検証**: `tls:` ブロック無しで `sslpolicy-id` と `sslcert-id` の
> annotationだけを付けたIngressで、ILBがHTTPSに切り替わること(および
> IDCFの管理Webhookがこの形を受け付けること)は、まだ実機で確認していない。
> HTTPSにならない場合は、上記の `describe ingress` のEventsを確認すること。

## 2. 停止(一時停止・コスト抑制)

**設定やデータ(PVC/ConfigMap/Secret/Service/Ingress)は残したまま、
Podだけを止めたい場合:**

```bash
kubectl -n pii-masking-shield scale deployment/moya4 --replicas=0
```

再開する場合は元に戻すだけでよい(イメージやSecretの再作成は不要)。

```bash
kubectl -n pii-masking-shield scale deployment/moya4 --replicas=1
kubectl -n pii-masking-shield rollout status deployment/moya4
```

> **注意**: この操作はコンテナ(Pod)の計算リソースの課金を止めるだけで、
> IDCFクラウド側で申し込んだ **ILB自体の課金は止まらない**。ILBの利用を
> 一時的に止めたい場合は、IDCFクラウドのコンソールから別途対応する必要がある。

## 3. 更新(コード変更・設定変更の反映)

### アプリのコードを変更した場合

```bash
# 1. 新しいイメージをビルド・プッシュ(タグを変えることを推奨。
#    :latest の使い回しだとロールバック時にどのコードか分からなくなる)
docker build -t <REGISTRY>/moya4:2026-09-15 .
docker push <REGISTRY>/moya4:2026-09-15

# 2. kustomization.yaml の newTag を書き換える
#    (images: - name: moya4 / newTag: "2026-09-15")

# 3. 適用
kubectl apply -k k8s/
kubectl -n pii-masking-shield rollout status deployment/moya4
```

動作に問題があれば直前のバージョンに戻せる。

```bash
kubectl -n pii-masking-shield rollout undo deployment/moya4
```

### 環境変数(ConfigMap/Secret)だけを変更した場合

`k8s/configmap.yaml` を編集した場合や、Secretの値を
`kubectl create secret ... --dry-run=client -o yaml | kubectl apply -f -`
等で更新した場合、**ConfigMap/Secretの変更はPodへ自動反映されない**。
変更を反映するには、Podを再作成させる必要がある。

```bash
kubectl apply -k k8s/          # ConfigMapの内容を更新
kubectl -n pii-masking-shield rollout restart deployment/moya4
kubectl -n pii-masking-shield rollout status deployment/moya4
```

### ドメイン・TLS設定だけを変更した場合

`k8s/ingress.yaml` を編集して `kubectl apply -k k8s/` を実行するだけでよい
(Podの再起動は不要)。certbotが書き込んだ `ilb.idcfcloud.com/sslcert-id` は
マニフェストに書いていないため、`kubectl apply` しても消えない。

ドメインを変更する場合は、新しいドメインがidcf-dns-certbotの `CERT_DOMAIN`
(例: `*.pdpro.jp`)に含まれていることを確認すること。あわせてDNSのAレコード、
`k8s/configmap.yaml` の `OAUTH_REDIRECT_URI`(変更後は `rollout restart` が必要)、
Google Cloud Consoleの「承認済みのリダイレクトURI」も変更する。

## 4. 削除(後始末)

**このアプリに関するKubernetesリソースを全て削除する場合:**

```bash
kubectl delete -k k8s/
```

`k8s/namespace.yaml` がリソース一覧に含まれるため、この1コマンドで
Namespace(`pii-masking-shield`)ごと削除され、`kubectl create secret` で
別途作成した `moya4-secrets` / `moya4-registry-cred` を含め、この名前空間内の
リソースが全て一掃される。

> **⚠️ 重要**: Namespaceの削除により、監査ログを保存していたPVC
> (`moya4-logs`)も削除され、**中のログは復元できなくなる**。
> 削除前にログを保管しておきたい場合は、事前に取り出しておくこと。
>
> ```bash
> kubectl -n pii-masking-shield cp \
>   $(kubectl -n pii-masking-shield get pod -l app=moya4 -o jsonpath='{.items[0].metadata.name}'):/app/logs \
>   ./moya4-logs-backup
> ```

削除後、以下はKubernetesの外側(IDCFクラウド側)の後始末になるため、
必要に応じて別途対応する。

- **idcf-dns-certbotの反映先から外す**: Ingressを削除したまま、certbotの
  `k8s/cronjob.yaml` の `INGRESS_TARGETS` に `pii-masking-shield/moya4` が
  残っていると、次回の証明書更新時にIngressの更新に失敗してJobが異常終了する。
  アプリを撤去する場合は、`INGRESS_TARGETS` と `k8s/rbac.yaml` の該当ブロックを
  両方削除する(再デプロイする場合は残しておき、「TLS証明書」章の
  初回annotation付与を再実行する)。
- **ILBの契約解除**: このアプリ用に申し込んだILBをもう使わない場合、
  IDCFクラウドのコンソールから解除しないと課金が続く。他のアプリと共用
  している場合は解除しないこと。
- **コンテナレジストリ上のイメージ**: 不要になった場合は
  `docker rmi` や、レジストリ側の管理画面/APIで削除する。
- **クラスター自体**: 他に稼働中のアプリが無く、クラスターごと不要になった
  場合は、IDCFクラウドのコンソールからクラスターの削除を行う
  (このアプリのマニフェストの範囲外)。

## トラブルシューティング早見表

| 症状 | 主な原因 | 確認コマンド |
|---|---|---|
| Podが`Pending`のまま | PVCがbindできていない(StorageClass不一致) | `kubectl -n pii-masking-shield get pvc` / `kubectl get storageclass` |
| `ImagePullBackOff` | レジストリ認証Secット未設定・誤り、またはレジストリがHTTPS化されていない | `kubectl -n pii-masking-shield describe pod <pod名>` |
| Podは`Running`だが`Ready`にならない | 起動直後でspaCyモデル読み込み中(`startupProbe`待ち、数十秒かかることがある) | `kubectl -n pii-masking-shield logs deployment/moya4` |
| Ingress経由でアクセスできない | `ingressClassName` が実際のクラスタの名前と違う | `kubectl get ingressclass`(上記1章参照) |
| HTTPSでアクセスできない・証明書エラー | Ingressに `ilb.idcfcloud.com/sslcert-id` が付いていない(初回付与を忘れている、Ingressを作り直した)、またはcertbotのJobが失敗している(上記「TLS証明書(idcf-dns-certbotによる自動更新)」参照) | `kubectl -n pii-masking-shield get ingress moya4 -o yaml` / `kubectl -n cert-renew get jobs` |
| `kubectl apply -k` 後に古い証明書に戻った | `k8s/ingress.yaml` に `ilb.idcfcloud.com/sslcert-id` を固定値で書いている(マニフェストから削除し、`kubectl annotate` で現在のIDを付け直す) | `kubectl -n pii-masking-shield get ingress moya4 -o yaml` |
| `kubectl apply`が`admission webhook "validate-idcf-ingress.idcfcloud.com" denied`で失敗 | IngressのpathTypeが`ImplementationSpecific`以外になっている(IDCF独自の制約。`k8s/ingress.yaml`は対応済み) | `kubectl -n pii-masking-shield get ingress moya4 -o yaml \| Select-String pathType` |
| Ingressの`ADDRESS`が割り当てられない・`generateLB failed`エラー | `ilb.idcfcloud.com/sslpolicy-id` annotationが未設定、またはSSLポリシーIDが誤っている | `kubectl -n pii-masking-shield describe ingress moya4` |
| `generateLB failed: default server is not set` | バックエンドのServiceが`NodePort`になっていない(ClusterIPだとILBの振り分け先が作れない。`k8s/service.yaml`は対応済み) | `kubectl -n pii-masking-shield get svc moya4` |
| Googleログインで`redirect_uri_mismatch` | `OAUTH_REDIRECT_URI`(`k8s/configmap.yaml`)とGoogle Cloud Consoleの「承認済みのリダイレクトURI」が不一致 | `kubectl -n pii-masking-shield get configmap moya4-config -o yaml` |
