let headers
const uuid = () => Math.random().toString(36).slice(2) + '_test'

describe('CKAN Classic API Are Working', () => {
  beforeEach(function(){
    cy.fixture('aircan.json').as('testData').then(() => {
      headers = {'Authorization': this.testData.apiKey}
    })
  })

  const orgName = uuid()
  const packageName = uuid()

  it('API: Status Show', () => {
    cy.request({url: '/api/3/action/status_show',  headers: headers }).then((resp) => {
      expect(resp.body.success).to.eq(true)
    })
  })

  it('API: Package List', () => {
    cy.request({url: '/api/3/action/package_list',  headers: headers }).then((resp) => {
      expect(resp.body.success).to.eq(true)
    })
  })

  it('API: Group List', () => {
    cy.request({url: '/api/3/action/group_list',  headers: headers }).then((resp) => {
      expect(resp.body.success).to.eq(true)
    })
  })

  it('API: Tag List', () => {
    cy.request({url: '/api/3/action/tag_list',  headers: headers }).then((resp) => {
      expect(resp.body.success).to.eq(true)
    })
  })

  it('API: Package Search', () => {
    cy.request({url: '/api/3/action/package_search?q=GDX',  headers: headers }).then((resp) => {
      expect(resp.body.success).to.eq(true)
    })
  })

  it('API: Reasource Search', () => {
    cy.request({url: '/api/3/action/resource_search?query=name:GDX%20Resource',  headers: headers }).then((resp) => {
      expect(resp.body.success).to.eq(true)
    })
  })

  it('API: Organization Create', () => {
    cy.request({method: 'POST', url: '/api/3/action/organization_create', headers: headers, body: { name: orgName }}).then((resp) => {
      expect(resp.body.success).to.eq(true)
    })
  })

  it('API: Organization List', () => {
    cy.request({url: '/api/3/action/organization_list', headers: headers}).then((resp) => {
      expect(resp.body.success).to.eq(true)
    })
  })

  it('API: Organization Show', () => {
    cy.request({url: `/api/3/action/organization_show?id=${orgName}`, headers: headers}).then((resp) => {
      expect(resp.body.success).to.eq(true)
    })
  })

  it('API: Package Create', () => {
    cy.request({method: 'POST', url: '/api/3/action/package_create', headers: headers, body: { name: packageName, owner_org: orgName }}).then((resp) => {
      expect(resp.body.success).to.eq(true)
    })
  })

  it('API: Package Show', () => {
    cy.request({url: `/api/3/action/package_show?id=${packageName}`, headers: headers}).then((resp) => {
      expect(resp.body.success).to.eq(true)
    })
  })

  it('API: Package Delete', () => {
    cy.request({method: 'POST', url: '/api/3/action/package_delete', headers: headers, body: { id: packageName }}).then((resp) => {
      expect(resp.body.success).to.eq(true)
    })
  })

  it('API: Organization Delete', () => {
    cy.request({method: 'POST', url: '/api/3/action/organization_delete', headers: headers, body: { id: orgName }}).then((resp) => {
      expect(resp.body.success).to.eq(true)
    })
  })

  it('API: Recenty Chnaged Activity List', () => {
    cy.request({url: '/api/3/action/recently_changed_packages_activity_list',  headers: headers }).then((resp) => {
      expect(resp.body.success).to.eq(true)
    })
  })
})
