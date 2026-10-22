**The corpus is built, keyed, and checked; independent blind keying and human confirmation remain pending.**

## Counts and outcome

| Deliverable | Count or result |
|---|---:|
| Documents per set | 71 |
| Packets per set | 39 |
| Unique pages per set | 80 |
| Final clean PDFs | 110 |
| Final scan PDFs | 110 |
| Layer A truth files | 71 |
| Printed required non-boolean fields | 452 |
| Null required non-boolean fields | 13 |
| Decoys per set | 142 |
| Requested printed subtotal per set | 784 |
| Complete scored units per set | 797 |
| Billing plants | 3 |
| T1 scan pages | 20 |
| Source/key differences | 0 |

The 71 documents comprise 45 tickets, nine hauling logs, four invoices, four covers, four AFEs, and five JIB statements.
The 30 ticket packets contain 15 pairs and 15 singles.
Twelve carry T4/T5, with six pairs and six singles.
The remaining 18 lack ticket-count traps; some still carry field-label traps.
Four AFE packets and five JIB packets provide nine easy row-5 negatives.

Clean trap density is 288/797 (36.1%).
Scan trap density is 316/797 (39.6%).
Eight possible cover decoy traps remain excluded because downstream decoy selection is UNVERIFIED.
Every trap T1–T10 appears at least three times.
`README.md` contains composition, per-row density, rules, dependencies, and rebuild instructions.

## Gate 1 — build and all PDF hashes

1. `python3 src/build.py` exits 0 and prints 71 + 39 clean and 71 + 39 scan sha256 lines.

**PASS.** The command exited 0 after rendering, concatenation, keying, and checks.
Chrome aborted inside the sandbox; approved offline execution outside it succeeded.
The build keeps its profile inside this folder and disables background networking.

```text
command: python3 src/build.py
exit: 0
SHA256 clean document lines: 71
SHA256 clean packet lines: 39
SHA256 scan document lines: 71
SHA256 scan packet lines: 39
PASS: all 220 printed SHA256 values match the manifest.
```

Full command output, including all 220 SHA-256 lines:

```text
SHA256 clean document ticket_01 8a7725680a4537922d6aecbb708c5c95b2efa03541ea869fc5f80d02b1616970
SHA256 scan document ticket_01 ae00b7f3a5fbd0e7cadff828a1fac0aff7875c490763a07bba25512dca44f604
SHA256 clean document ticket_02 adcff84a312aaa7e6cf919644bdb2f85beb4d229bd9a9a2381466c1a26cf25c0
SHA256 scan document ticket_02 a8ff6f72015b9d0b71c58561c22fed3834f793df7ae3873a88b74973bd071fdb
SHA256 clean document haul_01 7954a3f9d0401e17efb8cea432460c273b0cf653735d625594e2d9474963afb0
SHA256 scan document haul_01 b06bd97c5c8338285c2a1d7d8f704383cdac13e236754b89f461c007cbe2cbea
SHA256 clean document ticket_03 bfdf7816077c042721ff1252f80146986bd449289a4e5a44ebf941455e443c06
SHA256 scan document ticket_03 30a912db2da79ab7467aad41e2b74b988f19ff3eb7dfc7be9890c3a0ed4a8253
SHA256 clean document ticket_04 b0ce3c276cb63d73ab2012b06767bc98f5ee33b718d85eb9a73e2ca9eb6c6e3d
SHA256 scan document ticket_04 e6d6e29d60b05311a75bc8a62eb3bbf821929fde0b11bcbe4ec7d439b790b951
SHA256 clean document haul_02 56382bd4600e563c4d89698e2a7df7171152c36ffcf2f7d7bfb5c90ff881b829
SHA256 scan document haul_02 c00fc6d207d52ad7789c183137e4c4550ddd13ae50f4cb8f581afeb514d7bc1f
SHA256 clean document ticket_05 2eb3429878f7e79c16489fe5ef093619d36ac36c0bf49139c9c09c655023b67c
SHA256 scan document ticket_05 ba8d2724bbe5d2c514e7bde3ac85d40117d3e52f96b484e7ea7f289133cafe15
SHA256 clean document ticket_06 c289d1b60f378ff7ddf46830c8136ab77328b6bb7a122b4b61321cfdff852b7b
SHA256 scan document ticket_06 6119ef016cba0e51d03d7cb9aa9740bfe83ee34375257d522375d9ec35dbff6e
SHA256 clean document haul_03 72311f76d59cc3d84b2c1c791f0f9ef34784d977e3382834f6d2272c32cfadaa
SHA256 scan document haul_03 35b0600270bbf7e9d06f3f269f5dc8d9c7e5a1ec7633282ab997665764cfb8ac
SHA256 clean document ticket_07 e31da47b089879cb2ea58def4c91f2b53b1edb83c4341c0fd85cb189bc273b4e
SHA256 scan document ticket_07 4c21c73a5d13fdd21d7b25e3e0d74164b5fb68026506153feb711fbaa7d4a18f
SHA256 clean document ticket_08 90d83f92d02b6f91746262c0df36d39ce22e8f48b12b687f2ff4ab7428f27fa4
SHA256 scan document ticket_08 0d4a0d2032d2a5ffaf1cf3b4af7e9bbd29d19c2e7f49f63b1f93de229f6fce73
SHA256 clean document invoice_01 162fbb6325c445d42b96e2f0ca36f0448157d0c39e343550f5c169b7174325e6
SHA256 scan document invoice_01 a2b89e8408095e2d8a19299c467ab60241da9a68e1b79e07114a3f0b7b984395
SHA256 clean document ticket_09 91e27fac70322e9b55d3097fca3e349c6d542b6bd85554b41253d27e61721813
SHA256 scan document ticket_09 a7d334300a130fd3d19fa94382778d13e62febd7163f9dd0f4b56b2753cb9801
SHA256 clean document ticket_10 4267af25eb59d1e3a46529231d14ef0030e355b4a5f18dc48ca00441a5716e9b
SHA256 scan document ticket_10 e0bef3ce1f83d72c3f1314059562cd0f0a692665792e996a381c442bd0c61bd2
SHA256 clean document invoice_03 88e332b61065e26ae9b5cd5667bca75b9b6ace2e864b6641267b8a64b4f9ea10
SHA256 scan document invoice_03 fbefcdaed43d493f38405b3d92715ef8f00b2dea81beb536bc823ea4d3006a3b
SHA256 clean document ticket_11 6592b18553180a3fa381969712f23df9f1d991206818101f4ed14d5f3e84ea5e
SHA256 scan document ticket_11 aa8f417b69eb979887f78bc5aea33b29333df8ce2d2a272d8685aba983db6e6c
SHA256 clean document ticket_12 9e622fbdf0f3d27042e161dc1378aa512d23bd37643a823334aa587ef15a0e9e
SHA256 scan document ticket_12 7b620b81886f9263b1bd1f99d0eccd8ea119cf873f9c0e672ad40c4f732e9dd4
SHA256 clean document invoice_04 1b3c39c265598e45f6bc6a1c7b9d2c038fe335fa0256dfb237ff61499c2ec4fb
SHA256 scan document invoice_04 2157971c0e9e2735b160f03abad6656fe79269b0748f35d60c5e0aecf3f5e6e3
SHA256 clean document ticket_13 0177dab59c0e7924019c5af590e03c50d8756e3b21429d5243e2efeff82b536f
SHA256 scan document ticket_13 5c1f1d72decd1da889fe61f58b6c9f8d8f73dfa82056111167b64070ee8aeea9
SHA256 clean document ticket_14 f0d5205b6938fbd59b87cc9fc6e6f8a9d60e9dde0ff428feef2f3116d8a86354
SHA256 scan document ticket_14 9029e715834c1771d0bc22cd817d3fe703175111ba8d9936fb7ee86fa39ca528
SHA256 clean document ticket_15 d69127774e22798f42c595a93f6e9fc21b23d96c0d4515e441fa76ad5feb0db7
SHA256 scan document ticket_15 1e8f31f1d17804474612d27a1ccbe098bab907da97355422bc134da67b2e4d75
SHA256 clean document ticket_16 8ce73a3f4fd0c2b9c1f2d473b3da88a42ed19aa406faaa4bc177715cc339a3a7
SHA256 scan document ticket_16 d33222b94391158c202598d3d38f4cf6d04f777b0aad9eaf12749a3f689e5c77
SHA256 clean document ticket_17 e889cca3b723deb2967bb93a86c213d59528cba3107aecd8e661b998d1eec22f
SHA256 scan document ticket_17 8fc5e8d67c244b041fb2b9b75730384546b20a1038f477bac71c244cdf81e783
SHA256 clean document ticket_18 9e953af03ce516bbd373c2a357143496480f4d169ab1956d855511e84305f3bb
SHA256 scan document ticket_18 e5527cc6bd0df254f02ce2e825acabc8eb190e0ba4c495735500011958bb1a92
SHA256 clean document ticket_19 6f122e1ffe02bac4b74cdf92d030515549b76b6cd757a05a35c1c111ce71e812
SHA256 scan document ticket_19 f1da365509e4d03fd5117d0a66a33688b80c34838f715e9b4803125fc57c6870
SHA256 clean document ticket_20 61dc3d6869b0c5badd343e068ce81f3d658a4bc70f7a51bb66904fc0d5184573
SHA256 scan document ticket_20 c1251cf996ba0f0a43adb1b0c841ea50b69cb502c67478975b02bb2667b3531e
SHA256 clean document haul_04 6849aec677203e34d35ecff6502ad85689d408054ce86d9247b4acc59fa40661
SHA256 scan document haul_04 9ff18d07cc641e322bae779f96ccac4088ea085cda4fbaa67f6b78114c9574be
SHA256 clean document ticket_21 a709185f37b607f3817a5cad791988ba38903d65455cac5f981341bffef2fd92
SHA256 scan document ticket_21 831e45b430c26a5208b4b69427b02ec2f24cb4e05c263e5a70cabd5a42e2f72d
SHA256 clean document ticket_22 ac3bd1770457607e91aaa7ff0e3e9df4ca3dfffa3a3ac35207c98e4067e5a925
SHA256 scan document ticket_22 f5c8b5a223341ab0c43ed7777abe86797375792d0a81f55655bb649f099e72ea
SHA256 clean document haul_05 33b12155f038052666a0cddd2ee44837860d29938581d03df6c9a8217925c402
SHA256 scan document haul_05 7e95768cc488231f78158897a287d9a18f70260e687998cb2a63e1e6c7b22d76
SHA256 clean document ticket_23 ce9d0db659e854aaf65c939fe1de84588e08e4b493b0658b63c0b10d787bf7f7
SHA256 scan document ticket_23 cc3b2bd63033377d78a9bb1d1f9877284b60feb4548d0c5c87c380f38b1c63af
SHA256 clean document ticket_24 44acd60465807150ee7a477b85425c807788dde0f0690a2b96955c2f4cc251e9
SHA256 scan document ticket_24 cd513e1d5d1c41a90621b622b504bcdf46ae84ed8a9ec51384c762eed17b2326
SHA256 clean document haul_06 4a68311700b44699ab79fa2e5b5bdbdcd548dd930953b35d0e28d06fa7c89c30
SHA256 scan document haul_06 f1cf883d8c1bf37b76dde3ffc7ecfce7c148b841d29f1ae14ec33d0087b14852
SHA256 clean document ticket_25 2ee95739f650ee7c1035bcc34c1563e1df55e5f1d6a1aba8fe599069ab770250
SHA256 scan document ticket_25 3c766cbb7ec102b4c14ca6eedccdb78380399cd5b1012b01b5851d96d732d4d8
SHA256 clean document ticket_26 629e598e6da7fe387a217c71182198e7411f7eae5beacb7ecc6fc8b96b4bfa6c
SHA256 scan document ticket_26 a3d8b6f1bd89493ac04507d41ec34081d0db2dfac29f07562f29415314bc44c2
SHA256 clean document ticket_27 6cdce1d9db26c954fe820d7da180b8bf60b2c76a6ea99caa5e61fcf420004a1b
SHA256 scan document ticket_27 82b2c994b7375215f0e12fd7b69a983aef6f9f6363e9bc784582f6c595bce8a6
SHA256 clean document ticket_28 352ccd024ec00134b22cfc34a1c96afc83ef361b1deb936d8d59690f05871014
SHA256 scan document ticket_28 8083029e66fcbb444608cb628d0b4cc4d677574065b3904ae9dc776ce6da01b3
SHA256 clean document ticket_29 08836011b9854c0ac2482de730d2d33a13c6473952cb7f72388588682d251a17
SHA256 scan document ticket_29 9891293db7cb134d6f9524187f3c5c354d3d6d649a2c71f8c3d956234da0ebd2
SHA256 clean document ticket_30 f45ce63e094321ceb6840632135775d61e2139fe7c984bf53c671b8ec225eef9
SHA256 scan document ticket_30 999aaa28e29a8f77048f7a4b17e285b3fb4c3d83f26c14c95ef1cdfaff84c4fd
SHA256 clean document ticket_31 60f044c355f881059ca455caac40e877faeac8cf9c2ec0311f8b2140f42720bf
SHA256 scan document ticket_31 ca6d0db67968cd2638221a02b61f3e2b8fb3f72002c529a223619488f4161fe7
SHA256 clean document ticket_32 af1e6f8ecb40b0df562d5f32eb971b780daa1cec7350d85450c98c78bcc32f59
SHA256 scan document ticket_32 c0631dae5020a37c3d305b2633dd150c642924d973fe5e8a7c6b59c579d61953
SHA256 clean document ticket_33 b2b4770562fb8e41f6cdd1604b7b468ba4bb00263a235cdebb039fd8157a1687
SHA256 scan document ticket_33 6209d051b75291e4d68bea2d9295565c32762d7d30f970ea6d3f8bbf9f10658e
SHA256 clean document ticket_34 04de9518579bcd5d3d9832fa5eac152754b0988b69424a55b994d0198b201dc5
SHA256 scan document ticket_34 3e1a621800b56f167e7ce5f42136ce5780d18f8b0fc84f6cfd3ce754b4b6f318
SHA256 clean document ticket_35 3fa754ed185e3e7d418a54c32d1fd3203807bce66fe71c96c44a3c5cf803b14f
SHA256 scan document ticket_35 00f01d276c0f853d06203333b3930242935128c5624a24c7c5497e6c706e9281
SHA256 clean document ticket_36 6fed8a5aad58160b342d81c49bab9b9452414d60c73fb5c5ab852e6a50c46867
SHA256 scan document ticket_36 3cefa78b4f794f436f7800ff27898063009657efed83a66b58143ab6f459da28
SHA256 clean document ticket_37 7e766ab0c0b024686891c181e9de0f8064a259e0bb6c827ed294c4cef3b6f04d
SHA256 scan document ticket_37 49015f1b9eb772ac19061f47c226a7f1d2523dc6dbd5a99b4c1ae7035543d1c0
SHA256 clean document ticket_38 4ead73ddae3756cbff3671aa5151c910a1916d45f7a5ae0a6094e642e5056c4a
SHA256 scan document ticket_38 5667ea9ba389953b6e0d212c7e462a3e8017ee77c2ac0a4a0de0e06061f43037
SHA256 clean document ticket_39 23243bd0a4224c52d8f4f0a7b8082227d530ceff5ed431c596333cbb165240eb
SHA256 scan document ticket_39 04a67b0f1926163662cf37a0f74109c8573196227adb5e5e12d67892155ec6c1
SHA256 clean document ticket_40 8f8f114ac29570648a0935d71484f52f6587bf8770ec46f58dc7ae4f76b96cc5
SHA256 scan document ticket_40 c16b2ede43761df3c59c2e1db28ab69c08aa161426d14e6051647ab437802c84
SHA256 clean document haul_07 fb1a031e1df727df878621f65ad5289463a1f67e45ba8f0884a76d7a671ec290
SHA256 scan document haul_07 46c50cc139f268286c2e51c18646a36d360b983b1564a226ac54a7a3a5302b5e
SHA256 clean document ticket_41 e902e1140f4476c8d2184051ea2a17b9ec5825e074ab7ca189d346d19e670661
SHA256 scan document ticket_41 21b910d804e13cadd4fc69f9f1ab35dca82758d91d6fff6ed6bc285d461eb235
SHA256 clean document ticket_42 2a11c7651b327295db9afa31fd49c911db8b48100141417cc8a46b7a0c55e2f2
SHA256 scan document ticket_42 715558bb9c50bd09c17a5a642151d6ded22178442297d03ecc3a35a1663fa8ae
SHA256 clean document haul_08 46c7da6e9abe328001153a115b4394acbda8e41275706635ce826bac20ebc7f3
SHA256 scan document haul_08 6c10b0a4fdd42e7c2e259193abcac70358ff8aee87f17272c4538da912a554ea
SHA256 clean document ticket_43 e8b462c4f1f1d550562983a0d4b0843121c1666229225eb4c205042ef51b74aa
SHA256 scan document ticket_43 0f549068799a534335c610c53a490cfd6a46d4cbe02f19a932997c09b6a9d498
SHA256 clean document ticket_44 9f0284228edcf65be380af1276e1395b52cf349030a34566061490e96671119f
SHA256 scan document ticket_44 62dceca7a98dd3eb8eb9865a6c3fcf5f1076fcb1c67eb28141cb1386faa53bee
SHA256 clean document haul_09 6b6aca8620bb9a7d761fc9f7a3b09394b85c55bea7753ef70ac4da39f4b7e4df
SHA256 scan document haul_09 f654d672087b94660fc01a85efbd3ed61374ec2d5665266a16d8408ae6a7d651
SHA256 clean document ticket_45 59caac1f5dd71233d26742ec20b00db8c13683b7d5e3516342f58d5eb4f67440
SHA256 scan document ticket_45 d76ad7c164ab99613daf39cb1309140ac91247c156f130e95486eb59333a3bac
SHA256 clean document invoice_02 63b501113a785ef1925297c5ca7784f0479013242b9d8ebd2b3dbf919d3f9f23
SHA256 scan document invoice_02 46e7995e603c6e25928e5ea6f839abd2e53452a8d5351788b66b624f7b002413
SHA256 clean document cover_01 e6e02ab48828d87381acd7c6cb9a5f6eda02a215e338985b646998b1b5306ecf
SHA256 scan document cover_01 c23282431871e33327a813952faa2373767d37db21b42e6c9dd38ec11268e108
SHA256 clean document afe_01 b37722e5ac5e9312eb43a47b8459b0ccd8b8303dc4ce3b3c59c9b7c331327f44
SHA256 scan document afe_01 ef0708253027b25d8a66b1b8861f70e9cb068dfa58d142f5d059bd23defc6877
SHA256 clean document cover_02 4c9a563ed5682b029f8e84ee4671c34a6a330806f982ec31a691749049644fd7
SHA256 scan document cover_02 3bf5c40015e964a5c3ec1bd01274c08c010433aa297cb10b29853c82bee7144b
SHA256 clean document afe_02 b54960282eeae1d68259888955a739d7da86b29addf1cef0b4143838441043c6
SHA256 scan document afe_02 c9902ae2731d79e3ee40fae8bca66d955543a044467c9cecb78fa74a9125328b
SHA256 clean document cover_03 57078c148e2b675a1b5a551d9287d2e237fa6d8afd7af1c5cb9ab59e5a64f639
SHA256 scan document cover_03 05976ca6e9d3c9ee8833f82505a87337eaeb660bb6444c93036b930dbd09fc20
SHA256 clean document afe_03 9561aa6b1e144328a3e04060bc87a2ba53775540012185c30091a15b7354f791
SHA256 scan document afe_03 a2b9ff33b770097b416cd21eab0082d3f3bb6025847abc519499459435f3f53d
SHA256 clean document cover_04 eaea16f6ece95ed7d628c648f5827a9bcabd2892d245a5ff10ed03ee6f487cac
SHA256 scan document cover_04 084f0b9cebb0964ca8fd73db15ba0127073e7392e874686372caa8bf8a7a36b8
SHA256 clean document afe_04 70ef4553dd6736c6a2478690a86033b07b216eabb377c7ea5cd65c4655c90795
SHA256 scan document afe_04 9bf5bea97a5b60e90e4691f33b1b9ba406c705fd64edf83316ac261fe3c8b59e
SHA256 clean document jib_01 78b7bc54803ac441d087f9ea16259066a9a9fc678ad4ee78d6273ac5bc2369fc
SHA256 scan document jib_01 03f2eb5bb6544bbe86c225d0b5e611bd6b5c3421980c76b7720cd65da2e2aee3
SHA256 clean document jib_02 3ab3795f4d2098b18631461f302467ecaa3a4b6f360bf9b6f58b55da51408e0d
SHA256 scan document jib_02 73cc5c8c6bfc598f8205d8714615019e5526ca14483798543336eda6d13de115
SHA256 clean document jib_03 170d9647acb3ac23176e4369b6f260fd1dd4852bfb9f770206206eb3abf85a2e
SHA256 scan document jib_03 8a73864844af3dec22c5840e1b40bc6c7a4c4145a17cd619b7869bf99cae46a1
SHA256 clean document jib_04 8cb08a1d5785689d2f15ae2c96ee3e39f1682c8b02909d92b01d57bafaf91fff
SHA256 scan document jib_04 b27370d207db052a5e9c21a1a6a77739b0b1e14e7384c3462d69d02410a7792e
SHA256 clean document jib_05 8d6e25766fbecf13a8489ef0b36dbd54ad5abbb1e97d8a6a7fcc76dce6e85973
SHA256 scan document jib_05 30744ddd05199c6bbe3f386ce3e918248ffeffe6b81f319e38162e9b99aa0187
SHA256 clean packet ticket_01 a8866008fac432b9f19a6874c0268dfb540b93279c86f98528413e5bfe370313
SHA256 scan packet ticket_01 f0e7052d2a8bbb9907b9c4d10ee0b31db2de7129909f9c8b7dd1019ae76d1189
SHA256 clean packet ticket_02 ccd4112d2f9860e953111c5d482120ca1d93d8c5afa893e1aa539c029551ea85
SHA256 scan packet ticket_02 14797935c845a7ee553d84cc5da838eada3ac8e1e9f76e8338741c506393ec4c
SHA256 clean packet ticket_03 a81a85eb0055d53381cf2d2add080632d8b06a04e247675bcd63a8950a53927c
SHA256 scan packet ticket_03 fe59f7cf559ea82c7dc59b44df319faf5123067970227b7119149f014cb89496
SHA256 clean packet ticket_04 50ba0558123d772888fc6361c1db67bf2d0f7c434b7f8123f219230762577497
SHA256 scan packet ticket_04 b53d5bc12abfb2bd0ddb0c5299a798b0440c67d28bc7247f2aae2aefab67c018
SHA256 clean packet ticket_05 9f77020fa2356ffec73cc2077ff10110119be0d8fba48f7c5db15cc130474424
SHA256 scan packet ticket_05 b5e92835f829c910715df45b502b05e3c6b1fd2f85cc50b136f514c2088652da
SHA256 clean packet ticket_06 65875f67d0e92cd3c6d90d2c3654e27ccca21a69f619dfc7f287c5a6dd1cb350
SHA256 scan packet ticket_06 f417f65fb56b6ab2a1da93511f6629a09063e41079b8bd0466c93bcee0c70413
SHA256 clean packet ticket_07 61dd2ae2c1c81b1d085b625dedb4fd02a7bcc30c1b09ecc32a7297f1ce9145e4
SHA256 scan packet ticket_07 50e40631eb0cf486c01ca618a8ea2085907d6b0059c7389b52f0d101c7c5c198
SHA256 clean packet ticket_08 271861fffc9276f6492b223828976d5f2097a893e58d25acaa7478f4662b0a1f
SHA256 scan packet ticket_08 4a28a75239c71788e3045431b422d61f96681ef1c0217da2f44ab88a93351729
SHA256 clean packet ticket_09 8d5653533eea5d5d32d2da568168a991a85feba3cb582937aee7ee13cd2a2701
SHA256 scan packet ticket_09 baa2cf8fc05a95a0f5588a6852275a4539fa5de7b0f9343d1b90f5ab7edc2baf
SHA256 clean packet ticket_10 f69f4c4f0909a9b5ce9ec46aa7f4dc3abc68f42758e99de8fd69d2c3ef932edf
SHA256 scan packet ticket_10 f970fdeb06d139f73bba7a76e7112bdab649c295925db501e9e7cab0a59c7ff6
SHA256 clean packet ticket_11 4bdd2d830684ef9992709935cffc44fa9e9323d1a74d85434e0625bd2fa65a71
SHA256 scan packet ticket_11 334e631b44524777bc98afa2d94b4c40ca4a6b08916eec02412c233361a4d38f
SHA256 clean packet ticket_12 30f5f5cdc5dba360098b00cd7221351949078d873a9ed029feefa12e0aac333a
SHA256 scan packet ticket_12 789489d065cb7a1089bfc29351e47c451e4aee21a5b289f9f4d8ddfd61765fb5
SHA256 clean packet ticket_13 aad645a0816304a338decf13738c7bb09b930362f118500dfaae9185a5b7d96e
SHA256 scan packet ticket_13 0f04e02f2e800035077144feeafb3a95400d6e35a3c8f944244bb92ba264cf2f
SHA256 clean packet ticket_14 8b309e542c02860796973be8040fd4e78177011ef3e8268c06401dd2a542b061
SHA256 scan packet ticket_14 daa7fcabb28481a5192f266056e79cc690988e0c876fef8c61bd431b529ad5f7
SHA256 clean packet ticket_15 c9a70779bbe4e688924be8c7a68e4b4dc41d51b234ac0c4915527e44adaac609
SHA256 scan packet ticket_15 3792e3d3cdd416483213ebda551306c414e82a783ac1c9179115d9f132c3caea
SHA256 clean packet ticket_16 416e06c5c7d598f70d066a80c1798e6cd98ba22b0dca019f25b10b6bd80e85f6
SHA256 scan packet ticket_16 863084c1c5413f322bea53ca95f5c2a10100bf0e4133f712cdc1f24fd8ffa7be
SHA256 clean packet ticket_17 7f2ce897003e4dbff4b70979902f0cf9e2235c664cebd6c6b4f6058eda73932f
SHA256 scan packet ticket_17 634580fe4cba54a37fb840a054301258705e5086b98cd0178e4d4c2b547c4e6c
SHA256 clean packet ticket_18 7ad26f4f12ecd6b81edaad8d594db31c1e27479c634cd07b5e3f3b412a764f61
SHA256 scan packet ticket_18 9a9bbba5dbbe89965f83857bd56ed55950d54097afd2606e2f0a90c9507384c1
SHA256 clean packet ticket_19 8539aacdf82673fd24106f290c3e84b5440673effbe34079db1db7bdc990f8b9
SHA256 scan packet ticket_19 f53edd28ae92ddaaeaa0a499dce657b16ac14c10a71c568f3b3d8d81ad9f1f02
SHA256 clean packet ticket_20 c7e09b3b728d47e03dfe03a6719c5edd0ddbf6a206e26941914bacf36eb5fe3a
SHA256 scan packet ticket_20 e5349ecde34f0cb5e5fefda8823bdc0c0477061f97ff30c44c2648df9235ae10
SHA256 clean packet ticket_21 8dd9b9dae62e576000c2405053cb9e35505af909dc734358e0346f87eb9352d7
SHA256 scan packet ticket_21 0d1d6ebf28a57757d249db8f73280e45075d26f36352a1c4dbfe9112842a9b39
SHA256 clean packet ticket_22 37385bd79e495c277976d8cde43582c951de9ef58e524a2d4957fa68fbef4844
SHA256 scan packet ticket_22 6ccff4c1a4380a0457ef1510669978b9b6f108358f94fa8cfdfeeea4da4369b2
SHA256 clean packet ticket_23 c12c9a9c57ed614c500b46fb03b14c5b2dd4377291c2df5d0a30912ce121df5f
SHA256 scan packet ticket_23 dcb254469ca7ea1e526e0a7f9502c49ce9602f7da1356f381d15a711d6f0200e
SHA256 clean packet ticket_24 c3e20e686834e415103cd6d6a7c5283523bb94e21e25ea5b437bc6ed4d23a308
SHA256 scan packet ticket_24 db4df84774187427b3b7c676593a5fa3e3c747e62c91c11fc9b18f91a9b0dd86
SHA256 clean packet ticket_25 d8cc7916eeb8f6d006d204dd8718845fa16b91ea2ef5b7dd7325aab7c185650e
SHA256 scan packet ticket_25 15335c1eade124c026552628838df06fd5d9271a7617d516c5a578e32a87799c
SHA256 clean packet ticket_26 2d66ac57ece223d1b3fc780df0336539583d15efb21f212e6fa8f667994c295e
SHA256 scan packet ticket_26 5fe49849c7a28a714e508c87d1eaa10ee7cc5f9772060fc40851857815b00550
SHA256 clean packet ticket_27 e4da1ef4ef93f7b3b0d5f7318c0caedf1ae397ba293a6174fc0593562e88f70d
SHA256 scan packet ticket_27 a15e36e713f172cbfed8c8c06a0c258a399ef3e04530dab9cad6793e55778ae8
SHA256 clean packet ticket_28 343537c8d503e79138784a1e5b4200c62f382f842028582be65371bd91d5e33d
SHA256 scan packet ticket_28 c2238776ee57ee5787f7082d2630ddf6e3f44eae71d710d2de7cae71767758cb
SHA256 clean packet ticket_29 c16c221487e69b121087d291b7366f0d791ef595c8563571c7e71e321adb551f
SHA256 scan packet ticket_29 b2b4e87db139d2376ff99c3931069e05021282c59a40e4d7c960d68bb1dbf07e
SHA256 clean packet ticket_30 dda95ceb158c2916490f1e34d5afe17789cc0b96d0be0c974227f54c24c60971
SHA256 scan packet ticket_30 0c0f4b04a8d46d758b7b21665f02e7540e9c94104c01b3265fa1fedc65dd3f99
SHA256 clean packet afe_01 b82e4fe4533145741b0f2c36e92be6eca863a44d12c5532ae8a3792c7f9054fe
SHA256 scan packet afe_01 a96db8053b8e2908d3c9529c426d572ccfb71de00d599be93354efae4938fe11
SHA256 clean packet afe_02 ec4d53757ac7b351e64a3409093a59e8c4bdb8c6774c2689fcbd7b6bd4b27650
SHA256 scan packet afe_02 92f845b59829a06bf31865114964e0c67ea11ffdd02aac9956b71abe57447e55
SHA256 clean packet afe_03 34117adb2daa744623306090f16d159b94ba56d6d8dacd4d7dd2c4e52acb2bcd
SHA256 scan packet afe_03 95fb8c8a95f5e28ac0c4c7be9d24968005b00c7feb8ab2ff115070f92e01d7a8
SHA256 clean packet afe_04 0419b761a9b2a7557691d6667f8102e430b4ffc0a3d00f89063a65ee8e2e065d
SHA256 scan packet afe_04 8b11b56bb1daf8ab0779ff3a849086e76ca0e2e4bb2744b15095f23e69cd036e
SHA256 clean packet jib_01 f2297f691bbc4403a73f655e758b6047d65630b225048c49ff4d0ad8151a9b24
SHA256 scan packet jib_01 89020e4aeb1030e9d46f5735f189a1559a47ea73610d5125fb37359fadc80ff0
SHA256 clean packet jib_02 7feed5b2eb95b415aad6a65fb41b961399996c9a77d9decdde9b7746982adc2d
SHA256 scan packet jib_02 a5065eff109d1c9fa6131214c9ac82ad6ecf599f2a4ab45e4c098bd9ed2d9523
SHA256 clean packet jib_03 ed83a99b2970672de3e70c976906d4c3973b337180f554bb6fe51f0371c85c69
SHA256 scan packet jib_03 4ef6aca8602d8b8852b9ba001f4d9766911fd7e55d07ab9e6e8c4ba1dcd7ce84
SHA256 clean packet jib_04 8b989dca752e330522e3a72a19de92577d2e83d92e11f2c94e29ec9f78535701
SHA256 scan packet jib_04 456b33a41ba910d7a504a4281e7ba05c3bbef75ac64083c0f0dd0781f6643e6e
SHA256 clean packet jib_05 79611e2f7f7202103edc0b7d47445e2b0158b9c33d494ef64f706d7323cd076d
SHA256 scan packet jib_05 ff159c7054b3fff3fe540308302770db627dffb6d59687da06e725c3756eb4c9
PDF BUILD OK: 71 documents, 39 packets, 80 pages per set
LAYER A: 71 PDF-derived keys; 0 source differences retained in uncertain.
PASS: 71 documents; 39 packets; 80 pages per set; 220 PDF hashes and page counts verified.
PASS: packet page coverage, packet content order, required fields, list row keys, 3 plants, T1-T10.
PASS: 80 clean document pages have non-empty extracted text.
clean: row1=71; row4=80; row5=39; row8 printed=452; decoys=142; requested subtotal=784.
clean: all presence questions include 13 absent REQUIRED slots; row8=607; total=797.
scan: row1=71; row4=80; row5=39; row8 printed=452; decoys=142; requested subtotal=784.
scan: all presence questions include 13 absent REQUIRED slots; row8=607; total=797.
Absent REQUIRED non-boolean fields: haul_04.well_name, ticket_40.afe_number, haul_07.well_name, ticket_41.total, ticket_42.afe_number, ticket_43.total, ticket_44.afe_number, haul_09.well_name, ticket_45.total, invoice_02.afe_number, invoice_02.total, afe_02.api_number, afe_04.api_number
Scan OCR and normal-zoom visual legibility require separate audit; this check does not certify either.
```

## Gate 2 — structure, truth, and arithmetic

2. `python3 src/check.py`: 71 documents, 39 packets, 80 pages; page_count matches `pypdf` for every clean and scan file; sha256 fields match the files; every split_truth covers every page of its packet exactly once; every truth file has every REQUIRED field key for its class and every LIST with the required row keys; prints the unit arithmetic per set: row1 = 71, row4 = 80, row5 = 39, row8 printed = count of non-null REQUIRED non-boolean fields (at most 465) + decoys 2 per document = 142; total at most 797.

**PASS.** The checker also verifies packet content order and the absence of scan text layers.
It verifies exactly 71 document PDFs and 39 packet PDFs in each set.
It verifies the sealed plant hash and each planted value in PDF-derived truth.

```text
$ python3 src/check.py
PASS: 71 documents; 39 packets; 80 pages per set; 220 PDF hashes and page counts verified.
PASS: packet page coverage, packet content order, required fields, list row keys, 3 plants, T1-T10.
PASS: 80 clean document pages have non-empty extracted text.
clean: row1=71; row4=80; row5=39; row8 printed=452; decoys=142; requested subtotal=784.
clean: all presence questions include 13 absent REQUIRED slots; row8=607; total=797.
scan: row1=71; row4=80; row5=39; row8 printed=452; decoys=142; requested subtotal=784.
scan: all presence questions include 13 absent REQUIRED slots; row8=607; total=797.
Absent REQUIRED non-boolean fields: haul_04.well_name, ticket_40.afe_number, haul_07.well_name, ticket_41.total, ticket_42.afe_number, ticket_43.total, ticket_44.afe_number, haul_09.well_name, ticket_45.total, invoice_02.afe_number, invoice_02.total, afe_02.api_number, afe_04.api_number
Scan OCR and normal-zoom visual legibility require separate audit; this check does not certify either.
exit=0
```

The requested subtotal omits 13 absent required fields.
Those fields remain scored negative answers, so the complete task totals 797 units per set.
The 142 decoys are the specified two-per-document allocation; the runner was not executed.

## Gate 3 — extraction and visual legibility

3. Extraction (pypdf) of every clean page is non-empty; every scan page visually legible; state UNVERIFIED for OCR legibility; list the T1 pages.

**PASS for clean extraction and Codex visual review; OCR and independent human confirmation remain UNVERIFIED.**

I inspected all 80 scan pages, including every T1 page, at 850×1100 pixels per Letter page.
This corresponds to 100 pixels per inch.
The inspected images exactly match the JPEG pixels embedded in the scan PDFs.
Packet checks confirm that concatenation preserves those pixels and their order.
All scored text remained readable; no unreadable units were identified.
Clipped paper margins do not remove scored values.
Blank signature blocks, null cells, N/A, TBD, and struck dates retain their intended distinctions.

`audit/visual-review.json` binds each review result to the inspected image's SHA-256.
`audit/review/` contains the two-page visual review sheets.
This author review does not replace the required independent human normal-zoom decision.

```text
$ python3 audit/gate3.py
PASS: pypdf extraction is non-empty on all 80 clean document pages and all 80 clean packet pages.
PASS: all 80 scan pages contain 1275x1650 grayscale JPEG pixels and no text layer.
PASS: embedded scan pixels exactly match the images used for visual review.
PASS: Codex visually inspected all 80 scan pages at 100 pixels per inch; no unreadable scored values identified.
UNVERIFIED: OCR legibility, document parser extraction survival, and independent human normal-zoom confirmation.
T1 pages (document-local):
  ticket_19: page 1, skew +2.4 degrees
  ticket_20: page 1, skew -2.8 degrees
  ticket_21: page 1, skew +3.1 degrees
  ticket_22: page 1, skew -2.3 degrees
  ticket_23: page 1, skew +2.6 degrees
  ticket_24: page 1, skew -3.0 degrees
  ticket_25: page 1, skew +2.4 degrees
  ticket_26: page 1, skew -2.8 degrees
  ticket_40: page 1, skew +3.1 degrees
  ticket_41: page 1, skew -2.3 degrees
  ticket_42: page 1, skew +2.6 degrees
  ticket_43: page 1, skew -3.0 degrees
  haul_04: page 1, skew +2.4 degrees
  haul_07: page 1, skew -2.8 degrees
  invoice_02: page 1, skew +3.1 degrees
  cover_02: page 1, skew -2.3 degrees
  cover_04: page 1, skew +2.6 degrees
  afe_02: page 1, skew -3.0 degrees
  afe_04: page 1, skew +2.4 degrees
  jib_01: page 2, skew -2.8 degrees
exit=0
```

The stamp coordinates account for page-local position after skew.
All 20 T1 pages contain a stamp overlapping a printed value.
The scan pass retains the authorized noise, skew, opacity, compression, and margin-clipping settings.
No model result informed those settings.

## Gate 4 — pilot proper-noun exclusion

4. `grep -ril` for every pilot proper noun (operator, non-operator, vendors, wells, county from `../synth-pilot/manifest.json` `story`) over `src/` and `truth/` returns nothing.

**PASS.** Each grep returned no output and exit 1, the expected no-match result.
The pilot story omits vendor names, so the authorized generator supplied those two names.
The check also includes the disposal-location name and distinctive name roots.

```text
$ python3 audit/gate4.py
$ grep -ril -- 'Zelvori Basin Operations LLC' src/ truth/
(no output)
exit=1
$ grep -ril -- 'Mavren Fold Interests LLC' src/ truth/
(no output)
exit=1
$ grep -ril -- 'Orvessa Field Services LLC' src/ truth/
(no output)
exit=1
$ grep -ril -- 'Telnori Fluid Transit LLC' src/ truth/
(no output)
exit=1
$ grep -ril -- 'Nacrevale 7-QH' src/ truth/
(no output)
exit=1
$ grep -ril -- 'Fennovar 2-RH' src/ truth/
(no output)
exit=1
$ grep -ril -- Velquorin src/ truth/
(no output)
exit=1
$ grep -ril -- Quenvori src/ truth/
(no output)
exit=1
$ grep -ril -- Zelvori src/ truth/
(no output)
exit=1
$ grep -ril -- Mavren src/ truth/
(no output)
exit=1
$ grep -ril -- Orvessa src/ truth/
(no output)
exit=1
$ grep -ril -- Telnori src/ truth/
(no output)
exit=1
$ grep -ril -- Nacrevale src/ truth/
(no output)
exit=1
$ grep -ril -- Fennovar src/ truth/
(no output)
exit=1
PASS: no pilot proper nouns appear in src/ or truth/.
exit=0
```

## Reproducibility and keying evidence

```text
$ python3 audit/repro_stamp.py
PASS: final jib_01 scan document and packet reproduce byte-for-byte after the continuation stamp fix.
PASS: 218/220 PDF hashes match the preceding full build; only the two corrected jib_01 scan files changed.
PASS: all 110 clean PDFs reproduced byte-for-byte across complete builds.
UNVERIFIED: byte reproducibility across different Chrome, Poppler, ImageMagick, Python, or font versions.
exit=0
```

The final continuation-page stamp correction changed only its scan document and scan packet.
A separate repeat reproduced those two files byte-for-byte.
The other 218 PDF hashes matched the preceding complete build.
Cross-version byte identity remains UNVERIFIED.

The six frozen schemas exactly match `src/field_contract.json`.
The keyer writes rendered-PDF candidates before opening source values for comparison.
All 71 truth files identify `codex (author key, layer A)` and `rendered PDF`.
Every required field and every list row retains a document-local page location.
The source comparison contains zero differences, and every `uncertain` list is empty.

R3 has one explicit narrative repetition: AFE 02 repeats its AFE number in the declined-election note on page 2.
The page-presence key counts that occurrence as printed.
Its T6 metadata excludes that repeated field.
Other missing page headers remain absent on their continuation pages.

Plant seal: `17dfb9fb755a4c7d7d39ef0911ed87df09c3ff72824fe0ddd011229372928832`.
The corpus uses September 2026, seed 931047, and new fictional names.
The final corpus contains no pilot document or pilot document reference.
Gate 4 records pilot names only as exclusion-test evidence.

No API key was read or set.
No service API, study runner, forbidden source directory, or git operation was used.
Existing files in `tools/` remain unchanged.
All authored deliverables and audit records remain inside this folder.

## Open questions and UNVERIFIED items

No unresolved question blocks the requested local build.
Independent blind layer A agreement and Frank's human adjudication remain pending.
OCR legibility, document parser extraction survival, downstream integration, and measured model difficulty remain UNVERIFIED.
The clean density is 36.1%, below the approximate 40% target; scan density is 39.6%.
The unchanged layouts and limited class counts do not establish generalization beyond this synthetic corpus.

Next, provide only the PDFs and frozen field list to the separate blind keying session.
Hide the source, author truth, traps, and plants from that session.

## Final message

**Completed the corpus and wrote [REPORT.md](synth-heldout/REPORT.md) with gates 1–4 pasted.**

- Each set contains 71 documents, 39 packets, and 80 pages; all 220 PDF hashes pass.
- All 71 PDF-derived keys pass field and list checks, with zero source differences.
- All scan pages passed Codex visual review; OCR legibility and independent human confirmation remain UNVERIFIED.
- Pilot-name checks pass, and nothing was committed.

Next: run the separate blind re-key using only PDFs and the frozen field list.
